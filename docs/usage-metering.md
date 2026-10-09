# Usage metering and cost model

P5-05 adds private technical accounting, not billing, credits or commercial prices.
PostgreSQL is authoritative. Redis/RQ still orchestrates processing; no new queue,
provider or service was introduced. The stable ML matrix is unchanged.

## Audit of the integrated baseline

Base: `origin/dev` at `75d78aa` (P5-04 and the CI baseline integrated).

| Boundary | Existing behavior | Metering implication |
| --- | --- | --- |
| `routers/transcriptions.py` | Validated object upload, ownership and job committed before RQ publish | Exact validated bytes; source of credential comes from resolved policy, not frontend assertions |
| `workers/transcription_worker.py` | Atomic queued claim; forked work horse; terminal result and Meeting committed together | One UUID per actual claimed attempt; duplicate delivery does not create another attempt |
| AssemblyAI engine / platform budget | One submission, bounded polling; durable platform/BYOK no-repeat guard | Reservation is admission control, **not** an invoice. A retry denied by the guard records no second external submission |
| Intelligence worker | Locked revision claim; no automatic repeat after interrupted paid inference | Each explicit regeneration is another revision/attempt; response usage captured before JSON/grounding validation |
| Legacy minutes | Compatibility job, no persisted Intelligence revision and no automatic RQ Retry configured | Each executed compatibility request gets its own attempt; interrupted responses can remain unknown |
| P5-04 storage | Private local implementation, opaque keys, materialization and deletion outbox | Put/deletion identities derived from a hash of the internal reference; no filename/path/key in ledger |
| Guest conversion | Locked exact server-side claim, no approximate user assignment | Same lock serializes late usage arrival; existing events transfer in the claim transaction |

## Implemented metric matrix

Status describes the measurement/observation, not necessarily the product result.
For example, provider tokens can be `completed` while the result attempt is `failed`.

| Metric | Source | Reliability / meaning | Unit | Availability |
| --- | --- | --- | --- | --- |
| `attempt` / `attempt_status` | PostgreSQL claim and Worker/recovery | One attempt counter; terminal state is a separate non-additive event | attempt / state | Transcription, Intelligence; legacy minutes execution |
| `audio_seconds` | FFmpeg normalization | Technical media duration, **not provider billing** | second | After conversion, including subsequent processing failures |
| `external_call` | Before provider invocation | Submission intent; `unknown` does not prove acceptance or billing | call | AssemblyAI, Gemini |
| `provider_state` | AssemblyAI polling | Completed/error/unknown observation | state | When polling returns or fails |
| `provider_audio_seconds` | AssemblyAI `audio_duration` | Provider-reported duration, never replaced with FFmpeg duration; **not an invoice** | second | If response supplies a finite nonnegative value |
| `input_tokens` | Gemini `prompt_token_count` | Reported prompt size, includes cache; audit-only to avoid duplicate price calculation | token | If exposed by response/SDK |
| `output_tokens` | Gemini `candidates_token_count` | Reported candidate tokens | token | If exposed by response/SDK |
| `total_tokens` | Gemini `total_token_count` | Audit-only aggregate; never added to component costs | token | If exposed by response/SDK |
| `cache_read_tokens` | Gemini `cached_content_token_count` | Reported cache portion of prompt | token | If exposed by response/SDK |
| `input_uncached_tokens` | Prompt minus cache | Derived only when both counts exist and are consistent | token | Conditional; otherwise null |
| `thinking_tokens`, `tool_tokens` | Gemini additional fields | Never inferred from audio/text length | token | Current inspected legacy SDK does **not** expose these fields; null |
| `unclassified_tokens` | Total minus available prompt/candidate/thinking categories | Arithmetic remainder, **not** proof of thinking/tool category; audit-only | token | Conditional; inconsistent counts yield null |
| `provider_latency_seconds` | Worker monotonic clock | Local elapsed Gemini call, not a provider billing unit | second | Including provider exceptions |
| `processing_seconds` | Worker monotonic clock | Attempt wall time incl. model initialization, provider wait, persistence/instrumentation; not GPU busy time | second | Normal termination, including caught failure; abrupt kills unknown |
| `stored_bytes` | Validated upload size | Exact accepted object bytes, once | byte | Newly admitted objects; historical uploads are not backfilled by guessing |
| `deleted_bytes` | Put ledger/journal and successful cleanup | Observed deletion, idempotent; missing object also completes existing intent | byte | Bytes known if original put is available; otherwise null/unattributed |
| `byte_seconds` | Bytes × observed put-to-cleanup elapsed | Observed occupancy, not vendor billing or exact physical deletion time; clock reversal yields null | byte_second | Closed lifetimes only; no guessed duration for active objects |
| Provider billed amount, GPU/CPU utilization, network egress | Not supplied/measured | Unknown | — | Not implemented |

The test image uses the existing legacy SDK `google-generativeai==0.8.5` solely
for mocked adapter tests. Its `UsageMetadata` exposes prompt/candidates/cache/total.
Production remains on the existing Worker dependency range; there is no SDK migration.
Newer categories are handled if available, but are not claimed as supported today.

Official semantic references (reviewed 2026-10-07):

- [Gemini UsageMetadata](https://ai.google.dev/api/generate-content#UsageMetadata): prompt includes cache; total and categories must not be priced twice.
- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing): model, category and pricing context matter. No values are copied as defaults.
- [AssemblyAI silence FAQ](https://www.assemblyai.com/docs/faq/am-i-charged-for-transcribing-silent-audio): speech time is not interchangeable with submitted media duration. Account tariff/invoice remains authoritative.

## Ledger, attribution and idempotency

Groq summaries additionally report real Chat Completions usage when returned:
prompt/completion/total and optional cache/reasoning details. Reasoning is a
subset of completion, never a second price. Missing fields stay null; versioned
operator rates and a separate cumulative authorization budget are documented
in [Groq intelligence](groq_intelligence.md). Private provider filters accept Groq;
this does not grant processing permissions or add monthly summary allowances.

Migration `20261007_0012` is additive: `usage_events`, `usage_prices` and nullable
attempt IDs on existing jobs/revisions. Downgrade refuses to discard populated
usage/pricing history. Never run it against the project database merely to test it.

An event UUID is deterministic for operation attempt + metric + phase. PostgreSQL's
primary key and nested insert transaction make re-delivery/concurrent inserts a
no-op. First observation wins; retries do not reprice the stored event. Reusing an
identifier for a different resource/provider/unit is rejected. A real local
reprocessing has a new claim UUID and legitimately adds another consumption event.

Guest has a real server-side Guest context, **not a fictitious internal user**.
`user_id` is null until the exact existing claim resolves it. Unresolved legacy
ownership remains unattributed. Late replay checks current identity/Guest claim;
deleted identities are not resurrected. Deleting a resource retains its numeric
reference and measurements; account deletion sets the user FK null. Usage is not
accessible by another account, including an administrator via these endpoints.

No transcripts, prompts, original filenames, object paths, API keys, credential
IDs/ciphertexts, authentication tokens or arbitrary metadata are stored in the ledger.

## Cost model and catalog

The catalog starts **empty**. No published price, free tier, exchange rate, customer
quota, commercial plan or invoice amount is invented. Monetary values use Decimal /
PostgreSQL Numeric and are serialized as strings.

Supported configured estimates:

- AssemblyAI: `provider_audio_seconds`; `universal-2+speakers` is a separate tariff
  from `universal-2`. Base-only pricing is never applied to detection-of-speakers jobs.
- Gemini: uncached input, output, cache read, thinking and tool counts **only where known**.
  Prompt-inclusive and total counts are never priceable. Unknown categories remain
  unknown even if other components can be estimated.
- Whisper: operator-supplied `processing_seconds` amortization estimate. No external
  API bill does not imply zero hosting/GPU cost. Wall time is not physical utilization.
- Storage: measured occupancy only; **no monetary estimator yet**. Prorating lifetimes
  across rate changes, billing periods, replication and vendor rounding is future work.

Rates are operator-supplied, append-only through the importer, keyed by catalog
version/provider/model/metric/unit, with currency, decimal unit price/quantity,
timezone-aware validity and an explicit HTTPS source without credentials/query.
Existing versions cannot be edited/reimported with different content. New versions
supersede from their own start; equal-start ambiguity produces unknown cost.
Validate that a rate applies to the actual account, tier, options and context before
importing. Tiered/token-threshold/provider invoice logic is **not** implemented.

Each event freezes price ID, currency and estimate at observation time. If pricing
lookup fails, its cost stays unknown after replay; later prices do not retroactively
invent an estimate. BYOK external estimates have `cost_scope=customer`, platform
estimates `usagi`; local infrastructure estimates are USAGI costs. No budget is
debited by the ledger and BYOK never consumes the existing platform budget.
Currencies are grouped separately; there is no FX conversion. Component estimates
are not a complete invoice or guaranteed total operation cost.

## Recovery and operational procedure

Default `USAGE_SPOOL_DIRECTORY=database/usage-spool` is outside the uploads scan and
inside the existing shared private `processing_data` volume. API, Worker and
maintenance must use the **same persistent directory**. If overridden, mount it
persistently on all these services. It must not be public or inside audio uploads.
Linux files/directories use 0600/0700; Windows deployments require equivalent ACLs.
Include this journal in controlled private backups together with PostgreSQL.

The producer writes a bounded content-free JSON event with fsync and atomic
no-overwrite publication before attempting PostgreSQL insertion. On a temporary
metrics write outage, the result still proceeds; replay never calls a provider.
If disk alone fails, normal measurements attempt direct database delivery. If both
disk and database are unavailable, exact observations cannot be guaranteed: a safe
error is logged, and the durable attempt may remain unknown. Never replace missing
consumption with zero or rerun a paid call to reconstruct it.

Deletion journals are written before retiring the existing deletion outbox record.
If journaling fails, cleanup intent stays retryable even when the file is already
absent. The Worker drains the journal at startup and its existing maintenance cycle.

Commands from `modules/backend` (Compose `maintenance` service can run the same CLI):

```sh
python scripts/usage_maintenance.py replay                # dry-run, validates pending entries
python scripts/usage_maintenance.py replay --apply        # idempotent delivery only
python scripts/usage_maintenance.py prices --catalog /private/verified-rates.json
python scripts/usage_maintenance.py prices --catalog /private/verified-rates.json --apply
```

Catalog JSON is a list of objects with exactly: `catalog_version`, `provider`,
`model`, `metric`, `unit`, `currency`, `unit_price` (decimal string), `unit_quantity`
(decimal string), `effective_from` (timezone ISO datetime), `effective_until`
(timezone ISO datetime or null) and `source` (verified HTTPS reference).
There is intentionally no bundled numeric example that could be mistaken for a tariff.

Reconciliation resolves pending journal delivery and lifecycle observations, **not
vendor invoices**. A kill between external acceptance and response capture may
leave an unknown paid attempt; existing no-repeat guards are preserved. There is no
new user cancellation endpoint; RQ `stopped`/`canceled` states are observed by recovery.
The legacy minutes flow's SDK-internal retries remain unobservable through its
existing interface; ledger invocation count is not a promise of provider request count.
Retention of accounting history is currently indefinite with identity anonymization;
a separately approved policy is needed before purging it. No automatic purge was added.

## Private API

- `GET /usage/events`: authenticated owner's measurements, limit 1–100, bounded offset.
- `GET /usage/summary`: grouped by provider, credential source, resource type,
  operation, metric, unit, currency and cost scope. Unknown counts stay explicit.

Optional filters: `after`/`before` (timezone-aware, half-open interval, ≤366 days;
default last 30), `provider`, `credential_source`, `resource_type`. Caller identity
filters are rejected; no public Guest or cross-user/admin aggregate endpoint exists.
Responses use `Cache-Control: no-store`. Report quantities per metric, **never sum
input/total/cache/derived counts or stored/deleted bytes as interchangeable usage**.
Time filtering selects observations, not prorated infrastructure occupancy in that
period. An occupancy lifetime is recorded at cleanup and may span earlier periods.

## Validation scope and remaining work

### Product-facing overview

`GET /usage/overview` is an additive, authenticated owner-only projection for
Settings → Plano e consumo. Only `after`/`before` are accepted, with the same
bounded, timezone-aware period (default last 30 days). It returns technical
`audio_seconds` for transcription and `attempt` for transcription/intelligence/
legacy minutes, grouped by operation, metric and unit. Missing quantities stay
explicit; failed attempts are not concealed. Minutes shown in the UI are measured
audio seconds divided by 60, not a provider invoice or unique delivered minutes.

The projection does not select or return internal costs, prices, currency,
credential provenance, provider details, resource identifiers or user identifiers.
The frontend calls this projection, not the cost-bearing events/summary endpoints.
Guest has no access; administrator status does not grant another user's usage.
No commercial plan, balance, checkout or subscription is implemented.

Automated tests use synthetic users, mocked providers and a disposable PostgreSQL/
Redis/RQ stack. They cover concurrency, delivery idempotency, retries/reprocessing,
result validation/persistence failure, unknown quantities, BYOK budget separation,
catalog history/Decimal, storage cleanup, Guest claim, privacy and API isolation.
No paid provider calls, real GPU benchmarks or production invoice validation are
required or claimed for this Task. SDK migration, complete provider invoice
reconciliation, physical infrastructure metering, live/prorated storage cost and
billing remain separate future work.
