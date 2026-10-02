# P2-C operational hardening (release gates remain)

This document records the implemented controls and the remaining release gates.
It does not supersede the database and privacy design in
`P2A_DATABASE.md` and `P2B_SECURITY_PRIVACY.md`.

## Rate limiting

Redis applies atomic fixed-window limits before password verification or audio
storage. Login uses independent IP and exact-account buckets (30 and 10
attempts per five minutes by default). The official
`POST /transcriptions/jobs` upload/job endpoint uses independent IP and
authenticated-user buckets (300 and 30 requests per hour). The IP upload
bucket runs before multipart parsing. Values are
`LOGIN_RATE_LIMIT_PER_IP`, `LOGIN_RATE_LIMIT_PER_ACCOUNT`,
`UPLOAD_RATE_LIMIT_PER_IP`, and `JOB_RATE_LIMIT_PER_USER`. A rejected
request returns HTTP 429 and `Retry-After`; Redis failure returns HTTP 503
without attempting login or saving an upload. Use the actual remote address,
not untrusted forwarded headers. Operators behind a shared reverse proxy
should tune the IP buckets to expected shared traffic.

## Secrets by service

Compose no longer injects the entire `.env` into every service. API receives
JWT/bootstrap-admin secrets, not Hugging Face, AssemblyAI, or Gemini
credentials. Worker receives only provider credentials, not JWT/admin secrets.
Migration and maintenance receive only database access. Provider status flags
(`*_CONFIGURED`) are non-secret API metadata; set them explicitly in the
deployment environment alongside actual Worker credentials. They do not grant
provider access. The build context excludes `.env` files, uploads, results,
and caches. Never publish `docker compose config` or `docker inspect`
output because those tools can reveal runtime environment values.

The Worker uses a dedicated `model_cache` volume. Do not mount it into API.
The API image remains CPU-only and imports no ML stack at startup.

## Retention and reconciliation runbook

Run from the repository root against the intended Compose project. The
`maintenance` service has no API/Worker credentials. Preview first and
inspect counts, then apply with an operator-approved retention policy:

```powershell
docker compose -f modules/backend/docker-compose.yml --profile maintenance run --rm maintenance
docker compose -f modules/backend/docker-compose.yml --profile maintenance run --rm maintenance python -m scripts.reconcile_audio_files --apply
docker compose -f modules/backend/docker-compose.yml --profile maintenance run --rm maintenance python -m scripts.apply_retention
docker compose -f modules/backend/docker-compose.yml --profile maintenance run --rm maintenance python -m scripts.apply_retention --apply
```

Set `TRANSCRIPTION_RETENTION_DAYS` and/or `AUDIT_RETENTION_DAYS` above
zero to enable database candidates. No scheduled deletion is installed;
schedule the same explicit dry-run/apply commands in your deployment
orchestrator after monitoring dry-run output. Database retention excludes
queued/processing transcriptions and jobs. File reconciliation protects active
job input paths. Both commands are idempotent and return non-zero when a
filesystem deletion fails; a subsequent run can retry. Existing output paths
are not printed in logs. A regular authenticated deletion of an active job
returns HTTP 409.

## Legacy ownership

The bridge `owner_sub` remains until the real deployment database is
audited. The local isolated test database had zero ownership rows, which is
not evidence about production data. Audit and optionally backfill only exact
matches to the unique `users.username`:

```powershell
docker compose -f modules/backend/docker-compose.yml --profile maintenance run --rm maintenance python -m scripts.report_unresolved_ownership
docker compose -f modules/backend/docker-compose.yml --profile maintenance run --rm maintenance python -m scripts.report_unresolved_ownership --apply-exact
```

The report prints unresolved ownership IDs, not subjects, by default. If any
remain, resolve with authoritative identity evidence before dropping the
bridge. Never assign by similar names or delete unresolved records. Only
after a real deployment audit reports zero unresolved rows should an Alembic
migration make `user_id` non-null and remove `owner_sub`.

## ML/CUDA release gate

The current paired matrix remains Torch/Torchaudio 2.2.2, Torchvision
0.17.2, Pyannote.audio 3.3.2, Pyannote.core 5.0.0,
Faster-Whisper 1.2.1, and CTranslate2 4.8.2 on the
CUDA 12.3.2/cuDNN 9 Worker image. The P1-B/P1-C fixtures remain the
quality gate. A Torch-only upgrade is prohibited. The scanner still finds
Torch advisories; exposure is limited to the isolated Worker, which only
processes authenticated uploads and loads configured/gated model artifacts.
This is mitigation, not a vulnerability fix.

A candidate Pyannote 4/Torch 2.8+ matrix changes the model-loading contract
and must be evaluated in a disposable image against the same GPU, CPU,
diarization, stability, and PT-BR quality fixtures before changing production
pins. Do not count a dependency resolver or build alone as acceptance.

## Validation caveats

Do not mark P2-C complete until the production ownership audit, ML
vulnerability decision, and a restore drill against the intended deployment
are recorded. The local test database is intentionally isolated from the
pre-existing unrelated PostgreSQL volume.

The isolated 2026-09-24 validation produced:

- Backend Worker image: 95 pytest tests passed, including PostgreSQL/Redis/RQ
  integration; zero skipped. API/test image's intended lightweight subset
  passed 37 tests. Running the *entire* audio suite in that light image fails
  at collection because it intentionally has no Librosa/ML stack.
- React Router 7.18.4, Vite 8.3.1, React 18.3.1: seven Vitest tests passed,
  ESLint passed without warnings, production build passed, and full/production
  `npm audit` reported zero findings. The in-app browser could not connect
  in this session, so there was no visual interactive walkthrough.
- Both final images passed `pip check`. `pip-audit` found zero issues in API
  and 23 scanner entries in Worker, all attributed to Torch 2.2.2. Build
  tools were raised to pip 26.2.1, setuptools 83.0.0, wheel 0.46.3.
- Final CUDA/FP16 `large-v3` on the FLEURS PT-BR 1-minute fixture: WER
  0.051471 and CER 0.008333, matching P1-B. The final two-speaker pipeline
  produced 12 segments, 2 speakers, and 84 words, matching P1-C. Final CPU
  INT8 ran successfully at RTF 0.51157. Three combined stability runs reused
  both engine instances, with roughly 1.81 GB resident RAM after warmup.
- API image startup and `/health` passed without Torch, Pyannote, models,
  CUDA, or an embedded `.env`. Compose API and Worker were healthy; API
  reported one RQ Worker. Alembic upgrade/downgrade/upgrade/check passed in
  a separate isolated project. A custom-format PostgreSQL backup restored a
  synthetic user row into a new test database. Maintenance dry-run and
  zero-candidate apply commands passed.
