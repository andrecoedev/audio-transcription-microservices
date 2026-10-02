# P2-C.2 — database origin, Pyannote 4 and SimpleWorker diagnosis

Validation: 2026-09-25, local development only. This report supplements
`P2C1_TECHNICAL_CLOSURE.md`. No production deployment was inspected or
homologated. The Pyannote 4 candidate was **not promoted**.

## 1. Database actually used and legacy data

The named `backend-postgres-1` container still mounts `backend_postgres_data`,
but `transcription_db` and the configured application role are absent. Only
`postgres` and an unrelated database are present. No application operation was
performed in that unrelated database or volume. The running `p2c` development
stack uses a separate `p2c_postgres_data` volume and its own
`transcription_db`; it was used only for synthetic operational probes, then
returned to zero transcriptions and jobs.

Read-only inventory found `database/transcriptions.db` (56 KiB; SQLite
integrity check `ok`). It contains one transcription, one job in `processing`,
zero users and zero ownership rows. Thus one transcription has no owner.
The job's referenced input file was not found on the development host. No
transcript, filename, identity or file path was printed. The source could be
old real data; it must not be discarded or silently assigned to a user.

**Decision:** do not initialize a new database in `backend_postgres_data` and
do not import this SQLite file yet. The request called for a backup/migration
plan before execution when legacy data exists; no import, ownership backfill,
`owner_sub` removal or volume deletion occurred.

Proposed gated procedure:

1. Confirm the intended application PostgreSQL target and whether this SQLite
   record is user data. Keep the unrelated PostgreSQL volume untouched. Stop
   any writer to the SQLite source and make a consistent SQLite backup with
   the SQLite backup API; retain associated audio/upload storage and verify
   integrity, counts and an offline restore.
2. Verify the missing input audio path and decide whether the `processing`
   record is recoverable or must be preserved as historical/failed data. Do
   not automatically enqueue it.
3. Create or select an **empty, explicitly authorized** application database
   on a dedicated project volume; run `alembic upgrade head`. Back up that
   target before import. Run the existing `migrate_sqlite_to_postgres.py`
   importer first in an isolated restore rehearsal, then on the authorized
   target only after comparing counts, IDs, JSONB, FKs, sequences and status.
4. Reconcile the unowned transcription only from trustworthy ownership
   evidence. Keep `owner_sub` while any ownership is unresolved. Validate a
   target `pg_dump`/`pg_restore` before treating migration as complete.

## 2. Controlled Pyannote 3.1 versus Community-1 comparison

The stable Worker was stopped after confirming zero active application jobs.
Stable and candidate images were then run **sequentially** on the same RTX
3060 12 GB, with the same six AMI audio files, the same generated references
from the verified AMI RTTM, and the same manifest. Audio hashes matched the
manifest; the source RTTM hash matched its recorded hash. Both runs used
`DiarizationErrorRate`, a 0.25-second collar, included overlap as primary
policy, the same duration bounds, and the same production filter
(`min_duration=0`, `silence_threshold=-100 dBFS`). Automatic and exact
`num_speakers` modes used the same options in both runs. Stored baseline and
candidate hypotheses were rescored in one candidate runtime; all rescored DER
values matched the recorded values exactly.

| AMI fixture | Automatic DER 3.1 → Community-1 | Known-count DER 3.1 → Community-1 |
|---|---:|---:|
| Clean 2-speaker | 22.639 → 18.769% | 18.769 → 18.769% |
| Unequal volume | 36.813 → 35.358% | 35.358 → 35.358% |
| Rapid turns | 15.207 → 14.939% | **15.207 → 21.862%** |
| Overlap | 18.698 → 13.818% | 13.901 → 13.818% |
| Far-field noise | 33.718 → 16.905% | 23.705 → 16.905% |
| Four speakers | 12.079 → 12.506% | **10.707 → 24.609%** |

On all 12 candidate inferences, direct enumeration of the model's native
`speaker_diarization` tracks exactly matched the production adapter's
`speaker_turns()` tuples (start, end, speaker). Clipping and the production
filter also preserved all segments and speaker labels on these fixtures.
This rules out a demonstrated integration loss. Same audio/reference,
collar, overlap, duration and filters, plus exact cross-runtime rescoring,
rule out a demonstrated evaluation/configuration change. The remaining DER
change is attributable to the different model output, especially speaker
clustering: in known-count rapid turns, confusion rose 5.540 → 12.194%; in
known-count four speakers, 4.502 → 18.404%. Missed speech and false-alarm
percentages were identical within each pair. This is a model-behavior
regression in the diagnostic mode, not a reason to tune fixture-specific
thresholds. The production Worker currently uses automatic mode, but the
diagnostic regression remains a quality gate.

## 3. Resources under equivalent GPU occupancy

The separate-process Torch CUDA peak allocation is more trustworthy here
than `nvidia-smi` GPU-total sampling, which includes Windows/other processes.
Both models were measured sequentially; no other project Worker was resident.
The first fixture includes cold-start effects and is not steady state.

| Automatic fixture | 3.1 RTF → Community-1 RTF | Process RAM peak MB | Torch CUDA peak allocated MB |
|---|---:|---:|---:|
| Clean (first) | 0.131 → 0.263 | 1,818 → 2,229 | 9,321 → **10,703** |
| Rapid turns | 0.037 → 0.043 | 1,799 → 2,209 | 1,629 → 1,630 |
| Four speakers | 0.055 → 0.088 | 1,858 → 2,249 | 1,629 → **9,726** |

The candidate's four-speaker automatic inference used substantially more
process-private GPU memory on this run, leaving little headroom on 12 GB.
The candidate's known-count four-speaker peak was about 1,630 MB, so the
automatic-mode spike is not simply model residency. No OOM occurred, but
this one-run result requires repeatability/headroom investigation before
promotion. Other AMI automatic fixtures had approximately 1,630 MB peak
Torch allocation in both images. CPU/INT8 combined processing from P2-C.1
(same candidate matrix) completed a 62.54-second PT-BR fixture in 141.56
seconds (RTF 2.263, RAM peak 4,240 MB, two speakers/12 segments/84 words);
it was not rerun in P2-C.2 and is not a performance endorsement.

## 4. SimpleWorker with CUDA and durable recovery

A dedicated synthetic RQ queue and the empty `p2c` development database were
used. The probe initialized CUDA successfully in a container started with
`--gpus all`; it exercised the real job claim, persistence and recovery
functions with a sleep-only processing stub. It did not load real models or
read user audio. All probe records were removed afterward.

| Observation | Result |
|---|---|
| Long job | At 39 seconds of a 45-second job, RQ Worker heartbeat was 39 seconds old while PostgreSQL and RQ both reported processing/started. `SimpleWorker` has no in-job periodic heartbeat. |
| Timeout | With a three-second RQ timeout and eight-second stub, PostgreSQL job/transcription became `failed`, but RQ marked the returned failure result `finished`; the two status sources disagree. |
| Abrupt kill | After killing only the synthetic CUDA Worker mid-job, PostgreSQL stayed `processing` and RQ stayed `started`. Immediate recovery returned zero. A restart with the same fixed worker name was rejected by RQ as already active. |
| Delayed recovery | Once RQ marked the old execution abandoned, recovery requeued one job; the second attempt completed. A further recovery pass returned zero, and attempts remained two (one killed, one completed). No concurrent or third processing was observed in this probe. Exactly-once external side effects are not proven. |

The production `run_worker.py` also uses a fixed Worker name, so the restart
failure is a concrete risk for the same pattern. RQ 1.16.2's `SimpleWorker`
is not suitable for an unqualified production recovery guarantee here.
The smallest CUDA-compatible alternative with the current RQ is to use the
standard forking Worker **without initializing CUDA/models in the parent**,
loading them only inside each child job. That restores parent-side supervision
and crash isolation but sacrifices model reuse and increases per-job latency.
A future RQ `SpawnWorker` evaluation is another option, but requires an RQ
upgrade and still needs measured model-loading cost. Neither alternative was
implemented in this diagnostic phase. A dedicated heartbeat/lease mechanism
for a persistent GPU process would be broader work.

The default Compose file intentionally runs a CPU/auto Worker and gives it
no GPU device request. The documented `docker-compose.gpu.yml` overlay
requests `gpus: all`; its configuration validated, but a full overlay-based
stack walkthrough was not run here. The CUDA operational probe used a
temporary `docker run --gpus all` container, not the default Compose Worker.

## 5. Validation and decision

- Full backend/integration suite: **104 passed** in the stable image and
  **104 passed** in the P2-C.2 candidate image; isolated PostgreSQL/Redis/RQ,
  no skips. New tests cover read-only SQLite inventory, input-file presence
  counts without path disclosure, and overlapping Pyannote 4 tracks.
- Alembic `current` on the isolated test database: `20260920_0002 (head)`;
  `alembic check`: no upgrade operations. No migration ran on the named
  `backend_postgres_data` volume.
- Disposable candidate Docker build and `pip check` passed. Stable and
  candidate `pip check` passed. Both default and GPU-overlay Compose configs
  passed. Real Pyannote GPU inference and the controlled six-fixture matrix
  passed functionally; the quality/resource gate did not.
- Frontend: 9 tests passed; lint and Vite build passed. No visual walkthrough
  or production deployment was claimed in this phase.
- Docker Desktop temporarily became unavailable after the tests and was
  restarted; the cause was not established. On return, the development API,
  PostgreSQL, Redis and one Worker were healthy. Do not attribute the Docker
  interruption to GPU load without additional evidence.

**Decision:** keep the stable ML matrix and existing `owner_sub` bridge.
P2-C remains **not complete**. Resolve the legacy record's provenance,
ownership and missing audio before database import; address the SimpleWorker
heartbeat/restart/recovery gap; repeat the Community-1 four-speaker GPU peak
and make an explicit quality decision before ML promotion. Local evidence is
not production homologation.
