# P2-B identity, security, privacy, and data lifecycle

> Historical phase record: Redis rate limits and service-specific credentials
> were subsequently implemented in `P2C_OPERATIONAL_HARDENING.md`. Persistent
> meetings/intelligence extend export and erasure in P3-A/P3-B. Current
> dependency findings and consolidation decisions are in `CONSOLIDATION_AUDIT.md`.

PostgreSQL remains the source of truth. P2-B adds persistent local identity,
stable ownership, minimum auditability, explicit retention, and technical
export/erasure capabilities without organizations, RBAC, or external identity
providers.

## Identity and ownership

Before P2-B, login validated configuration directly, JWT `sub` was a mutable
username, and ownership existed only as `transcription_owners.owner_sub`.
The `users` table was not consulted during normal authentication.

The effective flow is now:

```text
local login -> users row/password hash -> JWT sub=user.id
            -> transcription_owners.user_id -> transcription -> job
```

The configured administrator is bootstrapped into `users` on its first valid
login. Existing database users authenticate against their stored bcrypt hash.
Create other local users interactively (the password uses `getpass`, not a
command-line argument):

```powershell
python scripts/create_local_user.py --username alice --email alice@example.com
```

`owner_sub` remains temporarily as a legacy bridge. Migration
`20260920_0002` backfills `user_id` only when `owner_sub` exactly equals a
unique stored username. It never assigns an unmatched row. Report unresolved
rows without exposing usernames by default:

```powershell
python scripts/report_unresolved_ownership.py
```

An exact legacy username is also reconciled on successful login. New ownership
always stores `user_id`; authorization uses it first. Cross-user and unresolved
resource access returns 404 to avoid resource enumeration. Administrators keep
operational access to all records.

## Endpoint authorization matrix

| Endpoint | Authentication | Ownership/authorization |
| --- | --- | --- |
| `POST /auth/login`, `GET /auth/config` | Public | No private resource |
| `GET /auth/me` | Bearer JWT | Persistent active user |
| `POST /transcriptions/jobs` | `transcribe` | New row owned by caller |
| `GET /transcriptions` | `read_transcriptions` | Owner-filtered; admin sees all |
| `GET /transcriptions/{id}` | `read_transcriptions` | Owner or admin |
| `GET /transcriptions/{id}/status` and jobs alias | `read_transcriptions` | Owner or admin |
| `DELETE /transcriptions/{id}` | `delete_transcriptions` | Owner or admin |
| `GET /stats` | `read_transcriptions` | Owner-scoped; admin sees global |
| `POST /meeting-minutes/generate` | `meeting_minutes` | Transcription owner or admin |
| `GET /meeting-minutes/status` | `meeting_minutes` | Authenticated scope |
| `GET /api-keys` | Admin | Status booleans only; never key material |
| `POST /api-keys` | Admin | Retired with 410; deployment-owned secrets |
| `/health`, `/system/gpu` | Public | No user data; GPU endpoint deprecated |

Old rollout flags still parse for environment compatibility, but private routes
never become anonymous when a flag is false.

## JWT, password, CORS, and HTTP controls

- JWT uses configured HMAC SHA-2 and requires `sub`, `exp`, `iat`, issuer,
  audience, and random `jti`. New `sub` is the numeric user ID.
- A short-lived username-`sub` compatibility path succeeds only when the exact
  persistent user exists. Deleted or inactive users cannot use new tokens.
- Production rejects missing/placeholder/short JWT secrets, wildcard CORS,
  permissive auth, demo login, and disabled protection flags.
- Passwords use bcrypt cost 12. Plaintext is never stored. Inputs beyond
  bcrypt's 72-byte limit fail instead of being silently truncated.
- Origins use `CORS_ALLOWED_ORIGINS`; credentials are disabled by default.
  Methods and headers are allow-listed.
- Responses add `nosniff`, frame denial, no-referrer, a restrictive permissions
  policy, and `no-store` for sensitive endpoint families.
- HTTPS, HSTS, TLS termination, trusted proxy headers, perimeter request-size
  enforcement, and log rotation remain deployment responsibilities.
- Distributed rate limiting was evaluated but deferred. Add a small Redis
  fixed-window policy before public Internet exposure; no second service is
  justified now.

## Credentials

`HF_TOKEN`, `AAI_API_KEY`, `GEMINI_API_KEY`, `SECRET_KEY`, database credentials,
and Redis credentials are infrastructure secrets. The application reads them
only from its process environment; deployments may populate that environment
from Docker secrets or a future external secret manager.
The shared `database/api_keys.json` and locally generated Fernet master-key
mechanism were removed. React no longer accepts secrets, and API status returns
only booleans.

There is no true per-user provider credential consumer. Therefore P2-B does not
add an encrypted-credential table or an unnecessary master-key lifecycle.

## Logs and errors

Logging installs a redacting filter/formatter for bearer tokens,
key/token/secret/password assignments, PostgreSQL URL passwords, email
addresses, and exception text. Job IDs, durations, providers, counts, and state
transitions may be logged. Transcript/minutes content, original filenames,
local paths, emails, tokens, and keys must not be logged. Client failures remain
short public messages; technical traces stay server-side and are redacted.

## Audio and derived-data lifecycle

```text
upload -> opaque database/uploads file -> queued/processing job
       -> worker temp/wav_<uuid>.wav normalization
       -> explicit local or AssemblyAI processing -> PostgreSQL result
       -> normalized WAV deleted in processing finally
       -> original upload deleted in worker finally (completed or failed)
```

The frontend has no post-processing audio download/playback feature, so the
privacy default is immediate original-audio deletion. A queue or process crash
leaves it available for RQ recovery. Active `queued`/`processing` paths are
protected from reconciliation. Completed/failed leftovers and unreferenced
uploads older than `AUDIO_ORPHAN_RETENTION_HOURS` (24 hours by default) are
candidates for the dry-run-first command:

```powershell
python -m scripts.reconcile_audio_files
python -m scripts.reconcile_audio_files --apply
```

Deletion is idempotent. Database deletion is transactional; filesystem removal
is after commit because it cannot join that transaction. A failed removal is
logged without its path and later reconciled.

| Data | Effective default |
| --- | --- |
| Original upload | Deleted after completed/failed; orphan grace 24 h |
| Normalized WAV | Deleted in `finally` |
| Transcriptions/segments | `TRANSCRIPTION_RETENTION_DAYS=0`: indefinite |
| Meeting minutes | RQ result only; TTL equals request timeout |
| Audit events | `AUDIT_RETENTION_DAYS=0`: indefinite |
| Logs | Deployment-managed rotation; no content/secrets |

Non-zero database policies run only via explicit dry-run-first maintenance:

```powershell
python -m scripts.apply_retention
python -m scripts.apply_retention --apply
```

There is no cancellation or retry-after-failure API. RQ recovery covers
queued/processing work; a failed job has minimized its original and must be
resubmitted.

## Export, erasure, and audit

The internal utility exports `usagi-user-export-v1` JSON with identity, owned
transcriptions/segments, safe job metadata, and the user's audit events. It
excludes hashes, secrets, and internal paths.

```powershell
python scripts/manage_user_data.py export --username alice --output alice-export.json
python scripts/manage_user_data.py delete --username alice --confirm alice
```

Erasure deletes owned transcriptions transactionally; FKs cascade jobs and
ownership. It then deletes the user and attempts idempotent file cleanup. Audit
actor FKs use `SET NULL`, retaining events without username/email. Minutes are
not durable in SQL and expire from Redis.

Events: `user.login`, `transcription.created`, `transcription.completed`,
`transcription.failed`, `transcription.deleted`, `user.data_exported`, and
`user.data_deleted`. Metadata contains only provider, diarization flag, stage,
reason, and counts—never content, credentials, IP, or user agent. There is no audit CRUD
endpoint. This is application-level append-only, not a cryptographic ledger;
database administrators and the explicit retention tool remain able to delete.

## External data flows

| Provider | Data sent | When | Optional |
| --- | --- | --- | --- |
| Faster-Whisper | Nothing leaves worker | Explicit `whisper` | Default local |
| Pyannote | Nothing during inference | Diarization enabled | Yes |
| Hugging Face Hub | Model/token request, not runtime audio | Initial model acquisition | Yes |
| AssemblyAI | Uploaded/normalized audio | Explicit `assemblyai`; never fallback | Yes |
| Gemini | Transcript and meeting context | Explicit minutes request | Yes |

Local Faster-Whisper plus Pyannote never calls AssemblyAI or Gemini. Provider
selection is validated and never silently changes from local to cloud.

## Upload and dependency audit

Uploads use an opaque UUID filename and validate size, allow-listed extension,
non-empty content, and supported magic bytes before persistence. User-supplied
path components are discarded. MIME and filename are not treated as proof of
content; FFmpeg errors become generic processing failures.

The P2-B audit on 2026-09-24 produced:

- API Python requirements: no known vulnerabilities and `pip check` clean.
- Worker Python requirements: `pip check` clean; 23 advisories are all on
  `torch==2.2.2`. A standalone upgrade is deferred because Torch, Torchaudio,
  Torchvision, Pyannote, and the CUDA runtime must move as a tested matrix.
- Frontend runtime: zero high/critical findings and two moderate React Router
  findings. The complete tree has one high finding in the Vite development
  server and three moderate findings. Remaining fixes require major upgrades to
  React Router 7 and Vite 8; `npm audit fix --force` was deliberately not used.
- Compatible npm lockfile updates were applied, including patched Axios,
  PostCSS, Rollup, and transitive packages. The production build passes.

## Backup/restore

Use the custom-format procedure in `P2A_DATABASE.md`. P2-B validation restored
synthetic users, transcriptions, jobs, ownership, JSONB segments, and audit
events into a second clean PostgreSQL 16 instance. Protect production dumps as
sensitive data and test restores periodically.
