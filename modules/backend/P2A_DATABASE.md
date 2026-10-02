# P2-A database architecture and operations

> This is the P2-A design record. Identity/ownership evolved in
> `P2B_SECURITY_PRIVACY.md`; current supervised Worker operations are in
> `USAGI_OPERATIONAL_STABILIZATION.md`. Preserve the original decisions below
> as historical context, not as a replacement for the current README.

> Historical P2-A note: P2-B retired `database/api_keys.json` and its local
> encryption-key file. Provider credentials now come only from the deployment
> environment; see `P2B_SECURITY_PRIVACY.md`.

PostgreSQL 16 is the only official development/production runtime database.
SQLite remains useful only for isolated unit tests and as the source format of
legacy local data. Production schema creation is exclusively Alembic-managed;
application imports and startup never call `Base.metadata.create_all()`.

## Audited persistence inventory

| Model/storage | Table/location | Fields and relationships | Current use | P2-A finding |
| --- | --- | --- | --- | --- |
| `Transcription` | `transcriptions` | Integer PK; upload metadata; model flags; status/error; JSON segments; result metrics; timestamps; 1:1 job and ownership | API list/result/status and worker result | Status and numeric values had no constraints; generic JSON; no relationship metadata |
| `TranscriptionJob` | `transcription_jobs` | Integer PK; unique FK to transcription; input path/options; status/error; lifecycle timestamps | RQ durable state and recovery | Previously had no FK/cascade, no status constraint, and no lifecycle timestamps |
| `TranscriptionOwnership` | `transcription_owners` | Integer PK; unique FK to transcription; indexed external JWT subject | Read/write authorization | Previously had no FK, allowing orphans |
| `User` | `users` | Integer PK; unique username/email; password hash; active/superuser; timestamps | Reserved local-user record; current login is config/JWT based | Defaults/nullability and unique constraint names were implicit |
| Meeting minutes | RQ result only | No SQL table | Synchronous compatibility endpoint delegates Gemini to worker | No durable minutes entity exists, so no schema was invented in P2-A |
| Provider API keys | `database/api_keys.json` | Fernet-encrypted values when an encryption key is configured | API/worker provider configuration | Not SQL data; migration to a secret manager is future security work |

Before P2-A, `src.database` created a SQLite engine and executed
`Base.metadata.create_all()` during import. API and worker each used their own
SQLAlchemy session, but the worker held one Session object across the complete
ML execution. `TranscriptionJob.transcription_id` and
`TranscriptionOwnership.transcription_id` were plain integers rather than
foreign keys. Deletes compensated with three manual ORM deletes.

## Official schema

```text
transcriptions (1)
    |-- (0..1) transcription_jobs       ON DELETE CASCADE
    `-- (0..1) transcription_owners     ON DELETE CASCADE

users                                  no FK yet
transcription_owners.owner_sub          external JWT subject, indexed
```

The ownership subject deliberately does not reference `users.username`.
Authentication currently supports configured/admin and external-style JWT
subjects without inserting a `users` row. Adding that FK today would reject
valid authenticated uploads. Jobs inherit privacy through their mandatory
transcription FK. Legacy ownerless transcriptions remain possible only for the
documented permissive-auth compatibility path; strict mode denies them.

Integers remain the PK strategy because public routes already use them and a
mass UUID migration has no demonstrated benefit in this phase. PostgreSQL
`TIMESTAMPTZ` is used for timestamps; worker timestamps are created with aware
UTC datetimes. `started_at`, `completed_at`, and `failed_at` belong only to the
job, where they describe the current execution attempt.

Statuses remain readable strings with database `CHECK` constraints accepting
only `queued`, `processing`, `completed`, or `failed`. This avoids the
operational friction of PostgreSQL native enum alterations while still
preventing invalid persisted values.

Segments use PostgreSQL JSONB. The product currently reads/writes a transcript
as one aggregate, and does not query or update individual segments. A segment
table would add write and join cost without a current query. JSONB preserves
lists, nested objects, empty values and Unicode, and allows targeted GIN or
expression indexes later. Before P3 full-text/speaker search, measure real
payloads and normalize only fields that need independent indexing or updates.

## Transactions and concurrency

The API dependency creates one Session per request, rolls it back when an
exception escapes, and always closes it. PostgreSQL pooling defaults per
process are intentionally small: `pool_size=5`, `max_overflow=5`, checkout
timeout 30 seconds, recycle 1800 seconds, with `pool_pre_ping` enabled. API and
worker are separate processes and therefore have independent pools.

Job creation commits the transcription, job and ownership together before RQ
publication. If Redis publication fails, both durable statuses are changed to
`failed` with a safe public message. This is not distributed two-phase commit;
P0 recovery remains the reconciliation mechanism.

The worker claims work with an atomic conditional update (`queued` to
`processing`). Only one concurrent delivery can claim a row. It then closes
the Session, runs audio/ML without an open database transaction, and uses a
new short transaction to persist the result and mark both records completed.
A failure similarly updates both records in one short transaction and stores
no stack trace in the public columns. Recovery resets an orphan processing job
to queued durably before publishing it again.

## Alembic

From `modules/backend` with a PostgreSQL `DATABASE_URL`:

```powershell
alembic current
alembic history
alembic upgrade head
alembic downgrade -1
alembic upgrade head
alembic check
```

The initial revision is `20260909_0001`. It creates all four tables, JSONB,
foreign keys/cascades, unique constraints, checks, indexes, and timezone-aware
timestamps from an empty database. Alembic intentionally rejects SQLite.

Compose uses one one-shot `migrate` service. API and worker depend on its
successful completion, so they never race to apply schema changes.

## Docker runtime

Copy `.env.example` to `.env`, replace development placeholders, then run:

```powershell
docker compose up --build
```

Official services are `postgres`, `redis`, `migrate`, `api`, and `worker`.
PostgreSQL and Redis have healthchecks and named volumes. PostgreSQL has no
published host port. The optional `test` profile adds only the P2 integration
runner:

```powershell
docker compose --profile test run --rm test
```

`/health` reports API, PostgreSQL, Redis, and RQ worker state separately. A
database failure produces `status=degraded` and `postgresql=unavailable`
without exposing connection strings.

## Importing an existing SQLite database

Do not point the application at the old file and do not copy it automatically.
Keep an immutable backup, migrate an empty PostgreSQL target, stop writers,
then run the explicit importer:

```powershell
copy database\transcriptions.db database\transcriptions.pre-p2a.db
alembic upgrade head
python scripts\migrate_sqlite_to_postgres.py database\transcriptions.pre-p2a.db
```

The importer requires an empty target, copies tables in FK-safe order,
preserves integer IDs/JSON/Unicode, maps legacy `done` to `completed`, resets
PostgreSQL sequences, and performs the target copy in one transaction. It
aborts on duplicates, invalid status, orphan ownership/job rows, or constraint
violations instead of silently dropping data. Validate record counts and a
sample of results before archiving the source.

## Backup and restore

Use custom-format backups. Replace service/container parameters through the
environment; do not put passwords in command history.

```powershell
docker compose exec -T postgres pg_dump -U transcription -d transcription_db -Fc -f /tmp/transcription.dump
docker compose cp postgres:/tmp/transcription.dump .\backups\transcription.dump

docker compose cp .\backups\transcription.dump postgres:/tmp/transcription.dump
docker compose exec -T postgres pg_restore -U transcription -d transcription_db --clean --if-exists /tmp/transcription.dump
```

Test restores regularly in a separate database. Stop API/worker or coordinate
a maintenance window before a destructive `--clean` restore.
