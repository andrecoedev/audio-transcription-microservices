from src.models import Meeting, MeetingSpeaker, Transcription, TranscriptionJob, TranscriptionOwnership


def _seed_meeting(session_factory, *, user_id=1, username="alice", title="Reunião"):
    db = session_factory()
    try:
        transcription = Transcription(
            filename="stored.wav",
            original_filename="meeting.wav",
            file_size_mb=0.01,
            duration_seconds=3.0,
            transcription_model="whisper",
            use_diarization=True,
            status="completed",
            segments=[
                {"start": 2.0, "end": 3.0, "speaker": "SPEAKER_01", "text": "segundo"},
                {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00", "text": "primeiro"},
            ],
            num_speakers=2,
            word_count=2,
        )
        db.add(transcription)
        db.flush()
        db.add(TranscriptionJob(
            transcription_id=transcription.id,
            input_path="unused.wav",
            transcription_model="whisper",
            use_diarization=True,
            status="completed",
        ))
        db.add(TranscriptionOwnership(
            transcription_id=transcription.id,
            owner_sub=username,
            user_id=user_id,
        ))
        db.add(Meeting(id=transcription.id, title=title, language="pt"))
        db.add_all([
            MeetingSpeaker(meeting_id=transcription.id, speaker_id="SPEAKER_00"),
            MeetingSpeaker(meeting_id=transcription.id, speaker_id="SPEAKER_01"),
        ])
        db.commit()
        return transcription.id
    finally:
        db.close()


def test_meeting_list_detail_and_transcript_are_owner_scoped(db_context, auth_headers):
    alice_id = _seed_meeting(db_context["session_factory"])
    bob_id = _seed_meeting(
        db_context["session_factory"], user_id=2, username="bob", title="Privada"
    )
    client = db_context["client"]

    anonymous = client.get("/meetings")
    assert anonymous.status_code == 401
    listing = client.get("/meetings", headers=auth_headers())
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["meetings"][0]["id"] == alice_id
    assert listing.json()["meetings"][0]["speaker_count"] == 2
    assert "segments" not in listing.json()["meetings"][0]

    detail = client.get(f"/meetings/{alice_id}", headers=auth_headers())
    assert detail.status_code == 200
    assert detail.json()["transcription_id"] == alice_id
    assert detail.json()["owner_user_id"] == 1
    assert detail.json()["language"] == "pt"

    transcript = client.get(f"/meetings/{alice_id}/transcript", headers=auth_headers())
    assert transcript.status_code == 200
    assert [segment["order"] for segment in transcript.json()["segments"]] == [0, 1]
    assert [segment["speaker"] for segment in transcript.json()["segments"]] == [
        "SPEAKER_00", "SPEAKER_01"
    ]
    assert transcript.json()["text"] == "primeiro\nsegundo"

    for path in (f"/meetings/{bob_id}", f"/meetings/{bob_id}/transcript"):
        assert client.get(path, headers=auth_headers()).status_code == 404
    assert client.patch(
        f"/meetings/{bob_id}", json={"title": "Invasão"}, headers=auth_headers()
    ).status_code == 404
    assert client.patch(
        f"/meetings/{bob_id}/speakers/SPEAKER_00",
        json={"display_name": "Invasão"}, headers=auth_headers(),
    ).status_code == 404
    assert client.delete(f"/meetings/{bob_id}", headers=auth_headers()).status_code == 404


def test_meeting_title_speaker_rename_and_cascade_delete(db_context, auth_headers):
    meeting_id = _seed_meeting(db_context["session_factory"])
    client = db_context["client"]
    headers = auth_headers()

    assert client.patch(
        f"/meetings/{meeting_id}", json={"title": "   "}, headers=headers
    ).status_code == 422
    updated = client.patch(
        f"/meetings/{meeting_id}", json={"title": "  Planejamento  "}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Planejamento"

    renamed = client.patch(
        f"/meetings/{meeting_id}/speakers/SPEAKER_01",
        json={"display_name": "  Maria  "},
        headers=headers,
    )
    assert renamed.status_code == 200
    assert renamed.json() == {"id": "SPEAKER_01", "display_name": "Maria"}
    assert client.patch(
        f"/meetings/{meeting_id}/speakers/UNKNOWN",
        json={"display_name": "Outra"}, headers=headers,
    ).status_code == 404
    transcript = client.get(f"/meetings/{meeting_id}/transcript", headers=headers).json()
    assert transcript["segments"][1]["speaker_display_name"] == "Maria"

    deleted = client.delete(f"/meetings/{meeting_id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"/meetings/{meeting_id}", headers=headers).status_code == 404
    assert client.get(f"/transcriptions/{meeting_id}", headers=headers).status_code == 404
    db = db_context["session_factory"]()
    try:
        assert db.get(Meeting, meeting_id) is None
        assert db.query(MeetingSpeaker).count() == 0
        assert db.query(TranscriptionOwnership).count() == 0
        assert db.query(TranscriptionJob).count() == 0
    finally:
        db.close()


def test_deleting_transcription_also_removes_meeting(db_context, auth_headers):
    meeting_id = _seed_meeting(db_context["session_factory"])
    response = db_context["client"].delete(
        f"/transcriptions/{meeting_id}", headers=auth_headers()
    )
    assert response.status_code == 200
    db = db_context["session_factory"]()
    try:
        assert db.get(Meeting, meeting_id) is None
        assert db.query(MeetingSpeaker).count() == 0
    finally:
        db.close()
