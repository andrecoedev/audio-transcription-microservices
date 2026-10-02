"""End-to-end HTTP smoke against an isolated development stack.

The caller supplies USAGI_SMOKE_PASSWORD only through the process environment.
No credential, token, transcript, or result body is printed.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import struct
import time
import wave
from pathlib import Path

import requests
from redis import Redis
from rq.exceptions import NoSuchJobError
from rq.job import Job


def _sample_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        for index in range(16000 * 8):
            sample = int(1800 * math.sin(2 * math.pi * 220 * index / 16000))
            audio.writeframesraw(struct.pack("<h", sample))
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diarization", action="store_true")
    parser.add_argument("--audio-file", type=Path)
    parser.add_argument("--require-segments", action="store_true")
    parser.add_argument("--meeting", action="store_true")
    parser.add_argument("--drop-rq-job", action="store_true")
    parser.add_argument("--intelligence", action="store_true")
    parser.add_argument("--review-output", type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if args.drop_rq_job and not args.meeting:
        parser.error("--drop-rq-job requires --meeting")
    if args.intelligence and not args.meeting:
        parser.error("--intelligence requires --meeting")

    password = os.environ["USAGI_SMOKE_PASSWORD"]
    base_url = os.environ.get("USAGI_SMOKE_API_URL", "http://api:2020")
    session = requests.Session()
    login = session.post(
        base_url + "/auth/login",
        json={"username": "admin", "password": password},
        timeout=20,
    )
    print(f"login_http={login.status_code}", flush=True)
    login.raise_for_status()
    session.headers["Authorization"] = "Bearer " + login.json()["access_token"]
    me = session.get(base_url + "/auth/me", timeout=20)
    print(f"session_http={me.status_code}", flush=True)
    me.raise_for_status()

    job_id = None
    meeting_ready = False
    try:
        audio_bytes = args.audio_file.read_bytes() if args.audio_file else _sample_wav()
        audio_name = args.audio_file.name if args.audio_file else "usagi-smoke.wav"
        created = session.post(
            base_url + "/transcriptions/jobs",
            files={"file": (audio_name, audio_bytes, "audio/wav")},
            data={
                "transcription_model": "whisper",
                "use_diarization": str(args.diarization).lower(),
            },
            timeout=30,
        )
        print(f"upload_job_http={created.status_code}", flush=True)
        created.raise_for_status()
        job_id = created.json()["transcription_id"]
        deadline = time.monotonic() + args.timeout
        last_state = None
        while time.monotonic() < deadline:
            polled = session.get(
                base_url + f"/transcriptions/jobs/{job_id}/status", timeout=20
            )
            polled.raise_for_status()
            state = polled.json()["job_status"]
            if state != last_state:
                print(f"job_state={state}", flush=True)
                last_state = state
            if state in {"completed", "failed"}:
                break
            time.sleep(2)
        else:
            raise TimeoutError("HTTP polling deadline exceeded")

        result = session.get(base_url + f"/transcriptions/{job_id}", timeout=20)
        print(f"result_http={result.status_code}", flush=True)
        result.raise_for_status()
        result_data = result.json()
        print(f"result_status={result_data['status']}", flush=True)
        print(f"result_segments={len(result_data.get('segments') or [])}", flush=True)
        print(f"result_speakers={result_data.get('num_speakers')}", flush=True)
        if state != "completed":
            raise RuntimeError("Transcription job did not complete")
        if args.require_segments and not result_data.get("segments"):
            raise RuntimeError("Completed transcription has no segments")
        if args.meeting:
            meeting = session.get(base_url + f"/meetings/{job_id}", timeout=20)
            print(f"meeting_http={meeting.status_code}", flush=True)
            meeting.raise_for_status()
            meeting_data = meeting.json()
            assert meeting_data["transcription_id"] == job_id
            transcript = session.get(base_url + f"/meetings/{job_id}/transcript", timeout=20)
            print(f"meeting_transcript_http={transcript.status_code}", flush=True)
            transcript.raise_for_status()
            assert len(transcript.json()["segments"]) == len(result_data["segments"])
            if args.drop_rq_job:
                connection = Redis.from_url(os.environ["REDIS_URL"])
                rq_id = f"transcription_{job_id}"
                rq_deadline = time.monotonic() + 30
                while time.monotonic() < rq_deadline:
                    rq_job = Job.fetch(rq_id, connection=connection)
                    if rq_job.get_status(refresh=True) == "finished":
                        break
                    time.sleep(1)
                else:
                    raise TimeoutError("RQ job did not reach finished state")
                rq_job.delete()
                try:
                    Job.fetch(rq_id, connection=connection)
                except NoSuchJobError:
                    pass
                else:
                    raise AssertionError("RQ job still exists")
                assert session.get(base_url + f"/meetings/{job_id}", timeout=20).status_code == 200
                assert session.get(base_url + f"/meetings/{job_id}/transcript", timeout=20).status_code == 200
                print("meeting_survived_rq_deletion=true", flush=True)
            if args.diarization:
                assert meeting_data["speakers"], "Diarization yielded no speaker IDs"
                speaker_id = meeting_data["speakers"][0]["id"]
                renamed = session.patch(
                    base_url + f"/meetings/{job_id}/speakers/{speaker_id}",
                    json={"display_name": "Falante de teste"},
                    timeout=20,
                )
                print(f"rename_speaker_http={renamed.status_code}", flush=True)
                renamed.raise_for_status()
                assert renamed.json()["display_name"] == "Falante de teste"
            meeting_ready = True
            availability = session.get(base_url + f"/meetings/{job_id}/intelligence/status", timeout=20)
            availability.raise_for_status()
            if not availability.json()["configured"]:
                unavailable = session.post(base_url + f"/meetings/{job_id}/intelligence", timeout=20)
                # Transcript validation precedes provider availability. A silent
                # synthetic sample may complete without any non-empty text.
                has_text = any(segment.get("text", "").strip() for segment in result_data["segments"])
                expected_status = 503 if has_text else 422
                print(f"intelligence_unconfigured_http={unavailable.status_code}", flush=True)
                assert unavailable.status_code == expected_status
            if args.intelligence:
                analysis = session.post(base_url + f"/meetings/{job_id}/intelligence", timeout=20)
                print(f"intelligence_request_http={analysis.status_code}", flush=True)
                analysis.raise_for_status()
                intelligence_id = analysis.json()["id"]
                deadline = time.monotonic() + args.timeout
                while time.monotonic() < deadline:
                    status = session.get(base_url + f"/meetings/{job_id}/intelligence/status", timeout=20)
                    status.raise_for_status()
                    analysis_state = status.json()["generation"]["status"]
                    if analysis_state in {"completed", "failed"}:
                        break
                    time.sleep(2)
                else:
                    raise TimeoutError("Intelligence polling deadline exceeded")
                print(f"intelligence_state={analysis_state}", flush=True)
                if analysis_state != "completed":
                    raise RuntimeError("Meeting analysis did not complete")
                analysis_result = session.get(base_url + f"/meetings/{job_id}/intelligence/result", timeout=20)
                print(f"intelligence_result_http={analysis_result.status_code}", flush=True)
                analysis_result.raise_for_status()
                content = analysis_result.json()["content"]
                print(f"intelligence_decisions={len(content['decisions'])} intelligence_tasks={len(content['action_items'])}", flush=True)
                if args.drop_rq_job:
                    connection = Redis.from_url(os.environ["REDIS_URL"])
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        rq_job = Job.fetch(f"meeting_intelligence_{intelligence_id}", connection=connection)
                        if rq_job.get_status(refresh=True) == "finished":
                            break
                        time.sleep(1)
                    else:
                        raise TimeoutError("Intelligence RQ completion deadline exceeded")
                    rq_job.delete()
                    assert session.get(base_url + f"/meetings/{job_id}/intelligence/result", timeout=20).status_code == 200
                    print("intelligence_survived_rq_deletion=true", flush=True)
                if args.review_output:
                    # Only for explicit public/non-sensitive smoke fixtures, never logs.
                    args.review_output.parent.mkdir(parents=True, exist_ok=True)
                    with args.review_output.open("x", encoding="utf-8") as review:
                        json.dump({"transcript": result_data["segments"], "analysis": analysis_result.json()}, review, ensure_ascii=False, indent=2)
    finally:
        if job_id is not None:
            deleted = session.delete(
                base_url + (
                    f"/meetings/{job_id}" if meeting_ready else f"/transcriptions/{job_id}"
                ),
                timeout=20,
            )
            print(f"delete_http={deleted.status_code}", flush=True)
            deleted.raise_for_status()
            missing = session.get(
                base_url + f"/transcriptions/{job_id}", timeout=20
            )
            print(f"deleted_read_http={missing.status_code}", flush=True)
            assert missing.status_code == 404


if __name__ == "__main__":
    main()
