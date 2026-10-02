# Consolidation: persistent meetings and intelligence

## Scope and baseline

One PR to `dev`, explicitly requested by the maintainer. No rewrite of existing
commits, migration history, ML promotion, SDK migration or P3-C implementation.
After `git fetch origin`, local `dev` was zero commits behind and seven ahead.
All seven belong to this project's accumulated evolution and remain unchanged:

| Commit | Responsibility |
|---|---|
| `a807e5d` | GPU diagnostics and frontend model configuration |
| `0967820` | P0 durable Redis/RQ jobs and upload validation |
| `c67ec92` | P1-A lightweight API / processing boundary |
| `51b9d44` | Faster-Whisper, bounded PCM processing and tests |
| `d298d89` | Stability benchmarks and resource monitoring |
| `ba522f9` | P1-B final validation and diarization filter regressions |
| `2a36b3f` | P1-C AMI robustness benchmarks and baseline evidence |

## Review and cleanup decisions

The accumulated changes span PostgreSQL/Alembic, persistent identity and
ownership, strict JWT authorization, privacy, rate limits, supervised RQ
recovery, container configuration, persistent meetings, intelligence revisions,
Gemini grounding/abstention, React integrations and regression tests.

- Removed `benchmarks/p2c1_pyannote_probe.py`: a disposable API discovery probe;
  the shared compatibility adapter, its tests and reproducible DER benchmark
  supersede its duplicated output conversion. No active imports or consumers.
- Removed `Dockerfile.worker.runtime.candidate`: a temporary two-file overlay
  over a locally named historical image, superseded by the supported stable
  Worker Dockerfile. It was not used by Compose or operational instructions.
- Retained `Dockerfile.worker.candidate` and normalized candidate audit pins:
  the unpromoted matrix remains explicitly separate from supported Compose.
  Its historical base-image prerequisite is intentional; it is not a default
  production build or a claim of current homologation.
- Retained `scripts/probe_simpleworker.py`: also exercises standard Worker,
  CUDA-after-fork, timeout, heartbeat, crash and automatic recovery. Its
  synthetic-only purpose is explicit; it is not the runtime entry point.
- Retained SimpleWorker in integration tests as an in-process mock-provider
  harness. Production uses `RecoveringWorker`, derived from supervised Worker.
- Retained the legacy meeting-minutes route, Worker and React page: the current
  sidebar, routes and API client still consume them. New intelligence shares
  the Gemini client; removing the legacy contract would be a product change.
- Retained all four applied Alembic revisions without rewriting them. The
  `owner_sub` bridge remains: unresolved legacy ownership must not be guessed.
- Retained operational CLIs for backup/inventory/import, identity, ownership,
  privacy export/erasure, retention/reconciliation and HTTP smoke tests.
- Retained synthetic Gemini fixtures, frozen results including failed trials,
  and stable/candidate DER results. They explain the accepted local scope and
  rejected ML promotion; they are not disposable success-only evidence.
- Existing removal of provider-key persistence and its unused UI guide belongs
  to security hardening. No replacement secret-storage mechanism was added.
- Caches, logs, generated audio/builds, local SQLite and backups are excluded
  from Git/build context. No legacy database, backup or Docker volume was deleted.

## Documentation map

- **Current operations:** README, P2A_DATABASE, P2B_SECURITY_PRIVACY and
  USAGI_OPERATIONAL_STABILIZATION. The last supersedes SimpleWorker guidance.
- **Current domain/contract:** P3A_MEETINGS and P3B_MEETING_INTELLIGENCE.
- **Historical release evidence:** P1B_FINAL_VALIDATION, P1C_VALIDATION,
  P2C_OPERATIONAL_HARDENING, P2C1_TECHNICAL_CLOSURE, P2C2_DIAGNOSTIC,
  P3B1_GEMINI_LOCAL_HOMOLOGATION and P3B2_GROUNDING_ABSTENTION.
  Earlier failures and intermediate metrics remain intact. P3-B.2 is the
  authoritative later local factual evaluation, not the earlier P3-B.1 verdict.
- **Original P1-A audit:** preserved in commit `c67ec92`; README no longer
  points to a file removed by the subsequent P1-B work.

## Security and validation boundaries

The local signing key was replaced by the maintainer, not by automation.
The recreated API confirmed only availability, absence from the project's
rejected values, successful login/JWT validation and invalid-token rejection.
No key fragments or key hashes were produced. Provider keys remain Worker-only
in Compose; API availability flags must be configured separately.

Credential scans compare local configured secrets in memory and report only
locations/categories. Historical token signatures were placeholders; the
historical configured database URL match was credential-free SQLite. Ignored
data/dumps are not staged. A final scan is required before push.

Validation results for the final HEAD belong in the PR; historical counts in
phase reports are not substituted for the new run. No new paid Gemini calls
are needed to organize Git history. Existing local evaluations are retained.
Production is not homologated. Pyannote 4 is not promoted. Literal grounding
is not a general semantic validator; human review and small-sample limitations
remain explicit in P3-B.2.

## Updated dependency audit (2026-10-02)

The runtime scan now reports **1 API finding**, and **24 Worker findings**:
PyJWT 2.14.0 (`PYSEC-2026-4141` / `GHSA-42vr-xj54-vc7v`) plus the existing
23 Torch entries. Earlier zero-API reports remain historical, not current.
The [maintainer advisory](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-42vr-xj54-vc7v)
describes an uncaught recursion error when parsing deeply nested payloads before
signature verification; 2.15.0 fixes it. This application does not use
PyJWKClient or `verify_signature=False`: `decode_access_token` checks the HMAC
signature with an explicit algorithm, issuer and audience before parsing.
The added regression exercises a 20,000-level forged payload through the
decoder and HTTP authentication, requiring 401 rather than an uncaught error.
That mitigation is not a library vulnerability fix. The dependency is preserved
in this consolidation; a small separately validated PyJWT update belongs in
security backlog, not an unreviewed ML/SDK upgrade.

Both images passed `pip check`. `pip-audit` was installed only into disposable
containers, never into the supported runtime image. The first attempted
manifest audit failed because its flags were inappropriate; scanning actual
installed dependencies completed and reported the findings above. Full/runtime
`npm audit` returned zero findings after retrying outside restricted networking.

## Consolidation validation before commit reconstruction

- Backend: **152 passed, 11 warnings**, zero failed/skipped, using the stable
  Worker image and isolated PostgreSQL/Redis/RQ. The previous 151 were preserved;
  the extra test covers the newly reported unsigned nested JWT payload.
- Frontend: **14 passed**, ESLint zero warnings, Vite production build passed.
- Docker API/Worker/migrate/test images built; both runtime `pip check` passed.
- Alembic upgrade, downgrade through all four revisions to base, upgrade to
  head and `alembic check` passed only in the synthetic `p3btest` database.
- Lightweight API boundary/startup and supervisor tests: 15 passed in the
  non-ML test image. Maintenance dry-runs had zero candidates/deletions.
- Python compilation, standard/GPU Compose validation and diff checks passed.
- No new GPU inference, paid Gemini calls or visual browser walkthrough were
  performed during Git consolidation. Earlier real local evidence remains
  explicitly attributed to its phase reports, not relabelled as a new run.
