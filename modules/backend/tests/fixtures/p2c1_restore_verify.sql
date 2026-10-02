-- Synthetic restore drill assertions. Fails with ON_ERROR_STOP=1 if data changed.
DO $$
BEGIN
  IF (SELECT count(*) FROM users) <> 2
     OR (SELECT count(*) FROM transcriptions) <> 2
     OR (SELECT count(*) FROM transcription_jobs) <> 2
     OR (SELECT count(*) FROM transcription_owners) <> 2
     OR (SELECT count(*) FROM audit_events) <> 1 THEN
    RAISE EXCEPTION 'restore count mismatch';
  END IF;
  IF (SELECT segments->0->>'text' FROM transcriptions WHERE id = 1) <> 'teste'
     OR (SELECT jsonb_typeof(segments) FROM transcriptions WHERE id = 2) <> 'array'
     OR (SELECT metadata->>'source' FROM audit_events WHERE id = 1)
        <> 'p2c1-restore-drill' THEN
    RAISE EXCEPTION 'restore JSONB mismatch';
  END IF;
  IF (SELECT version_num FROM alembic_version) <> '20260920_0002' THEN
    RAISE EXCEPTION 'restore migration mismatch';
  END IF;
  IF (SELECT count(*) FROM transcription_owners WHERE user_id IS NULL) <> 2
     OR (SELECT count(*) FROM transcription_owners WHERE owner_sub = 'alice') <> 1
     OR (SELECT count(*) FROM transcription_owners
         WHERE owner_sub = 'unknown-legacy-subject') <> 1 THEN
    RAISE EXCEPTION 'restore ownership mismatch';
  END IF;
  IF (SELECT count(*) FROM pg_constraint
      WHERE contype = 'f' AND connamespace = 'public'::regnamespace) <> 4 THEN
    RAISE EXCEPTION 'restore foreign key mismatch';
  END IF;
  IF EXISTS (
    SELECT 1 FROM transcription_owners o
    LEFT JOIN transcriptions t ON t.id = o.transcription_id
    WHERE t.id IS NULL
  ) OR EXISTS (
    SELECT 1 FROM transcription_jobs j
    LEFT JOIN transcriptions t ON t.id = j.transcription_id
    WHERE t.id IS NULL
  ) THEN
    RAISE EXCEPTION 'restore orphan reference';
  END IF;
END $$;

SELECT current_database() AS database,
       (SELECT count(*) FROM users) AS users,
       (SELECT count(*) FROM transcriptions) AS transcriptions,
       (SELECT count(*) FROM transcription_jobs) AS jobs,
       (SELECT count(*) FROM transcription_owners) AS owners,
       (SELECT count(*) FROM audit_events) AS audit_events,
       (SELECT version_num FROM alembic_version) AS migration;
