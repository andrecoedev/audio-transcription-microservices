"""One paid HTTP/RQ analysis of a frozen synthetic P3-B.1 source, never audio re-ASR."""
import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

import requests
from redis import Redis
from rq.job import Job

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import SessionLocal
from src.models import Meeting, MeetingSpeaker, Transcription, TranscriptionOwnership, User
from src.services.meeting_intelligence import fingerprint, snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', required=True, choices=['A', 'B', 'C'])
    parser.add_argument('--meeting-id', type=int)
    parser.add_argument('--delete', action='store_true')
    args = parser.parse_args()
    frozen = json.loads(Path(f'/tmp/p3b1-frozen/{args.fixture}.json').read_text(encoding='utf-8'))
    source = frozen['result']['source']
    assert fingerprint(source, frozen['segments']) == frozen['result']['input_fingerprint']
    session = requests.Session()
    base = 'http://api:2020'

    def call(method, path, **kwargs):
        response = session.request(method, base + path, timeout=30, **kwargs)
        if not response.ok:
            raise RuntimeError(f'HTTP {response.status_code}')
        return response.json()

    token = call('POST', '/auth/login', json={'username': 'admin', 'password': os.environ['USAGI_SMOKE_PASSWORD']})['access_token']
    session.headers['Authorization'] = 'Bearer ' + token
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username='admin', is_active=True).one()
        if args.meeting_id:
            meeting = db.get(Meeting, args.meeting_id)
            assert meeting and meeting.transcription.filename == f'p3b2-frozen-{args.fixture}.wav'
            assert meeting.transcription.ownership.user_id == user.id
        else:
            assert not args.delete
            transcription = Transcription(filename=f'p3b2-frozen-{args.fixture}.wav', original_filename=source['title'],
                file_size_mb=0, duration_seconds=frozen['duration_seconds'], transcription_model='whisper',
                use_diarization=True, segments=copy.deepcopy(frozen['segments']), num_speakers=frozen['meeting']['speaker_count'], status='completed')
            db.add(transcription)
            db.flush()
            meeting = Meeting(id=transcription.id, title=source['title'], language=source['language'])
            db.add(meeting)
            db.add(TranscriptionOwnership(transcription_id=transcription.id, user_id=user.id, owner_sub=user.username))
            for speaker in source['speakers']:
                db.add(MeetingSpeaker(meeting_id=meeting.id, speaker_id=speaker['id'], display_name=speaker['display_name']))
            db.commit()
            db.refresh(meeting)
        assert fingerprint(*snapshot(meeting)) == frozen['result']['input_fingerprint']
        mid = meeting.id
    finally:
        db.close()
    if args.delete:
        call('DELETE', f'/meetings/{mid}')
        print(f'fixture={args.fixture} test_meeting_deleted={mid}')
        return
    prefix = f'/meetings/{mid}/intelligence'
    status = call('GET', prefix + '/status')
    assert status['configured']
    previous = call('GET', prefix + '/result') if status['completed_revision'] else None
    started = time.monotonic()
    generation = call('POST', prefix + ('/regenerate' if previous else ''))
    assert generation['input_fingerprint'] == frozen['result']['input_fingerprint']
    assert call('POST', prefix + ('/regenerate' if previous else ''))['id'] == generation['id']
    if previous:
        assert call('GET', prefix + '/result')['revision'] == previous['revision']
        assert generation['revision'] == previous['revision'] + 1
    output = {'fixture': args.fixture, 'meeting_id': mid, 'generation': generation, 'attempted_calls': 1,
              'source_unchanged': True, 'previous_revision': previous['revision'] if previous else None}
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        status = call('GET', prefix + '/status')
        assert sum(item['status'] in ['pending', 'processing'] for item in status['revisions']) <= 1
        if status['generation']['status'] in ['completed', 'failed']:
            break
        time.sleep(2)
    output['status'] = status['generation']['status']
    output['polling_latency_seconds'] = time.monotonic() - started
    if output['status'] == 'completed':
        output['result'] = call('GET', prefix + '/result')
        if previous:
            assert call('GET', prefix + f'/result?revision={previous["revision"]}') == previous
        connection = Redis.from_url(os.environ['REDIS_URL'])
        job = Job.fetch(f'meeting_intelligence_{generation["id"]}', connection=connection)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if job.get_status(refresh=True) == 'finished':
                job.delete()
                break
            time.sleep(0.5)
        else:
            raise TimeoutError('RQ completion')
        assert call('GET', prefix + '/result') == output['result']
        output['survived_rq_deletion'] = True
    destination = Path('/tmp/p3b2-results')
    destination.mkdir(exist_ok=True)
    with (destination / f'{args.fixture}-v{generation["revision"]}.json').open('x', encoding='utf-8') as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2)
    print(f'fixture={args.fixture} meeting_id={mid} revision={generation["revision"]} status={output["status"]}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'replay_stopped={type(exc).__name__}', flush=True)
        raise SystemExit(1) from None
