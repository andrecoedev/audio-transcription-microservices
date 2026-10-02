# USAGI — local operational stabilization (2026-09-25/26)

This report supersedes the `SimpleWorker` runtime guidance in
[P2-C.2](P2C2_DIAGNOSTIC.md). It is **development-environment evidence**, not
production homologation. The Pyannote 4 candidate was not promoted.

## 1. Database origin and SQLite preservation

The pre-existing Compose project/volume containing unrelated databases was
not used for this application and was not queried or changed. The new project
`usagidev` has its own `usagidev_postgres_data` volume and database
`transcription_db`. The PostgreSQL image created the empty database; an
inspection confirmed **zero public tables before Alembic**. Schema creation
was exclusively `alembic upgrade head` through the official `migrate` service.

The legacy `database/transcriptions.db` remains untouched. Its local backup
directory contains:

- `transcriptions-legacy-20260925-exact.db` and `.db.json`: read-only,
  byte-for-byte SHA-256 match to source, matching modification time,
  `PRAGMA integrity_check=ok`, and manifest with original filesystem metadata.
- `transcriptions-legacy-20260925.db` and `.db.json`: independent SQLite online
  backup, also integrity-checked with identical table counts. Its byte hash
  differs because SQLite's backup API creates a logical snapshot; the exact
  copy above is the byte-preserving archive.

Each snapshot has 1 transcription, 1 job, 0 owners and 0 users. The job is
`processing`, has no available input audio and no ownership. It was **not**
imported or assigned to the development administrator. These backups are local
only; copy them to approved offline/offsite storage before relying on them for
disaster recovery. `owner_sub` remains in the schema; no ownership-removal
migration was made.

After the HTTP and synthetic tests, `usagidev` was at Alembic revision
`20260920_0002` with 1 locally bootstrapped user and 0 transcriptions, jobs or
owners. Authenticated creation/access/deletion and the ownership rules passed
in the smoke and integration tests. An isolated `usagitest` PostgreSQL volume
was used for the destructive integration-test truncations and Alembic
downgrade/upgrade; those operations were not run on `usagidev` or any unrelated
volume.

## 2. Worker decision and trade-off

| | Previous `SimpleWorker` (P2-C.2) | Current standard RQ `Worker` |
|---|---|---|
| CUDA/model lifetime | Loaded before jobs in one process and reused | Supervisor does not initialize CUDA; each forked child loads stable engines after fork |
| Heartbeat during a 45-second job | 39 seconds stale in prior probe | 1.7 seconds old when sampled during a 45-second CUDA-child probe |
| Three-second timeout | PostgreSQL `failed`, RQ `finished` | PostgreSQL `failed`, RQ `failed` |
| Immediate restart after kill | Fixed-name registration could block restart | Unique name restarts immediately; still-started job is not requeued |
| Model load cost | Amortized across jobs | Repeated per job; roughly 12.7–15.0 seconds of non-stage overhead in the measured smoke jobs |

`run_worker.py` now uses a uniquely named supervised RQ Worker. The child
initializes engines lazily only after the durable job is claimed. A safe
exception is re-raised after a failed job is persisted, so RQ and PostgreSQL
agree and neither RQ result nor logs need the original private exception.
Failed persistence also yields a safe RQ exception for later reconciliation.

RQ's existing maintenance cycle now calls the durable reconciliation every
60 seconds; no extra service or queue was added. Worker TTL is 75 seconds,
which makes the idle dequeue loop wake for maintenance. Transcription queue
timeout is configurable with `TRANSCRIPTION_JOB_TIMEOUT_SECONDS` (default
3600, minimum 60) in API and Worker, including recovered jobs. The longer
timeout permits long audio but also bounds **automatic orphan recovery only
after** RQ declares an old execution abandoned. With the default, a killed
job may wait about an hour plus maintenance delay. Never force an immediate
requeue of a still-`started` job: it could duplicate live inference.

## 3. Operational evidence

All probes used a separately named synthetic queue, generated records in
`usagidev`, a sleeping service and real PostgreSQL/RQ claim/persist/recovery
functions. The CUDA-child probes initialized CUDA after fork. They did not
read user audio. All probe records were removed after verification.

| Scenario | Observation |
|---|---|
| 45-second job | `processing/started` while running, heartbeat age 1.7 s, 1 attempt; then `completed/finished`, 1 attempt. |
| 3-second timeout, 12-second stub | Safe failure after CUDA init: DB job/transcription `failed`, RQ `failed`, 1 attempt. |
| Abrupt container kill | DB `processing`, RQ `started`; immediate reconciliation 0 and restarted Worker did not run in parallel. After RQ abandonment, 1 requeue and 1 successful second attempt; final `completed/finished`, 2 attempts. |
| Automatic recovery | A new Worker started immediately after a separate abrupt kill. Its normal maintenance later moved the abandoned job out of `started`, recovered exactly 1, and finished the second attempt automatically; final `completed/finished`, 2 attempts. |

The test proves behavior for one isolated Worker and synthetic processing. It
does not prove exactly-once effects for every external provider or a real
model process terminated at every possible point.

## 4. Stable ML and HTTP smoke

The default Dockerfile/requirements remain on Torch/Torchaudio 2.2.2,
Torchvision 0.17.2, Pyannote.audio 3.3.2, Faster-Whisper 1.2.1 and
CTranslate2 4.8.2. The separate Pyannote 4 candidate and its reports are
preserved; no candidate image or dependency was promoted. Only the stable
model cache was copied read-only from the old cache into the new development
volume; no database contents were copied.

The real Compose API/Worker stack had PostgreSQL, Redis and one Worker healthy.
Authenticated HTTP flow succeeded for login, session, WAV upload/job creation
(202), polling `queued → processing → completed`, result (200), deletion (200)
and subsequent 404. It succeeded both without diarization and with stable
Pyannote diarization. A further public PT-BR two-speaker fixture (62.54 s)
through the same HTTP flow produced 12 segments and 2 speakers; Worker metrics
were 26.32 s processing, RTF 0.4209, 6.061 s diarization and 6.573 s
transcription. Both HTTP flows were repeated after the final timeout/maintenance
changes; they completed and deleted their records, with the PT-BR fixture again
returning 12 segments and 2 speakers. The public fixture, not the generated
tone, is the combined-path speech evidence. No WER/DER comparison or
production quality claim was made in this phase.

The API image imported `src.main` with neither Torch nor Pyannote loaded. The
Worker supervisor test verifies it does not newly import Torch/Pyannote, and
the CUDA probe printed `parent_torch_imported=False` before forking. The
heavy models loaded in children. The new child per job has a measurable
latency cost; model reuse is intentionally sacrificed for RQ supervision and
CUDA fork safety.

## 5. Verification and remaining risks

- Full backend suite in the stable Worker image against isolated PostgreSQL,
  Redis and RQ: **111 passed**, 0 failed/skipped; 9 dependency deprecation
  warnings. The slim test image's selected Compose suite passed 38 tests. A
  deliberately broader `pytest -q` in that slim image cannot collect
  `test_diarization_filter.py` because the image intentionally has no ML
  dependencies; the complete suite was rerun successfully in the Worker image.
- Isolated `usagitest` Alembic check: no pending operations; downgrade one
  revision and upgrade to head passed. `usagidev` startup migration completed
  successfully and remained at head.
- Stable API and Worker Docker builds, `pip check` in both images, Python
  compile, GPU Compose `config --quiet`, API/DB/Redis/Worker health, and
  `git diff --check` passed. Git reported existing CRLF-to-LF notices, no
  whitespace errors.
- Frontend unchanged this phase: 9 Vitest tests, ESLint (zero warnings) and
  Vite build passed. No visual browser walkthrough or production deployment
  was claimed.

Development use of the existing product flows is now possible. For a
production release, the stable Torch advisory exposure and the unpromoted
Pyannote 4 quality/resource gate still need a separate decision; abrupt-job
recovery latency (up to the job timeout), per-job model reload and offsite
backup/restore procedures also need operational acceptance. The unowned
SQLite record remains intentionally excluded until provenance and audio are
resolved; do not infer an owner or silently discard it.
