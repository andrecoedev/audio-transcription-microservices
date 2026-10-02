-- Synthetic restore drill only. Run on a newly migrated, isolated database.
INSERT INTO users (username, email, hashed_password)
VALUES
  ('alice', 'alice@example.test', 'synthetic-not-a-real-hash'),
  ('bob', 'bob@example.test', 'synthetic-not-a-real-hash');

INSERT INTO transcriptions (
  filename, original_filename, file_size_mb, duration_seconds,
  transcription_model, segments, status
)
VALUES
  ('first.wav', 'first.wav', 1, 2, 'whisper',
   '[{"start": 0, "end": 2, "text": "teste", "speaker": "SPEAKER_00"}]'::jsonb,
   'completed'),
  ('second.wav', 'second.wav', 1, 3, 'whisper', '[]'::jsonb, 'completed');

INSERT INTO transcription_jobs (transcription_id, input_path, transcription_model, status)
VALUES (1, 'synthetic/first.wav', 'whisper', 'completed'),
       (2, 'synthetic/second.wav', 'whisper', 'completed');

INSERT INTO transcription_owners (transcription_id, owner_sub, user_id)
VALUES (1, 'alice', NULL), (2, 'unknown-legacy-subject', NULL);

INSERT INTO audit_events (
  actor_user_id, actor_type, event, resource_type, resource_id, metadata
)
VALUES (1, 'user', 'synthetic.restore', 'transcription', '1',
        '{"source": "p2c1-restore-drill", "safe": true}'::jsonb);
