# P2-C.1 technical and operational closure — not yet complete

## 2026-09-24 closure update (supersedes the earlier snapshot below)

The earlier 403 and "database not identified" observations below are retained
as an audit trail, not as the current state. Community-1 access now works with
the configured Worker token. The named PostgreSQL **container and volume** were
verified, but their **database contents do not match** the claimed application
database. P2-C remains **NOT COMPLETE**. No production ownership migration was
performed and the Pyannote 4 ML matrix was **not promoted**.

### Environment boundaries and database decision

| Boundary | Evidence | Action |
|---|---|---|
| Named development container `backend-postgres-1` | Compose labels: project `backend`, service `postgres`, configured Compose file; mount: `backend_postgres_data` at `/var/lib/postgresql/data` | Read-only inspection only |
| Contents of that volume | Non-template databases are `postgres` and `financas_db`; `transcription_db` is absent; the configured application role does not exist | Treat as the wrong cluster for this application despite matching container/volume names. No application-table counts, backup, backfill or migration were attempted there. Do not initialize a new database in this volume. |
| Isolated `p2c1drill` | Existing synthetic `pg_dump -Fc` / `pg_restore` drill; verification repeated on `transcription_restore_p2c1`: users 2, transcriptions 2, jobs 2, owners 2, audit events 1, Alembic `20260920_0002`; JSONB/FKs/ownership/orphans asserted by SQL | Synthetic procedure validated; **not** production restore evidence |
| Running development stack `p2c` | Separate `p2c_postgres_data`; initially 0 users; API/PG/Redis/Worker health healthy | Used only for synthetic HTTP smoke. After cleanup: 0 users, 0 jobs, 0 transcriptions. |

Because the actual project database is still not accessible, there is no
authoritative ownership count, no justified decision to remove `owner_sub`, and
no Alembic migration for that removal. The synthetic fixture still has one
unknown legacy subject, which the existing exact-match audit preserves.

### Pyannote 4 candidate quality and performance

The disposable `p2c1-worker-candidate` uses Torch/Torchaudio 2.10.0+cu128,
Torchvision 0.25.0+cu128, TorchCodec 0.10.0, Pyannote.audio 4.0.7/core 6.0.1,
Faster-Whisper 1.2.1, CTranslate2 4.8.2. The stable ML dependency matrix
remains Torch/Torchaudio 2.2.2, Torchvision 0.17.2, Pyannote.audio 3.3.2/core
5.0.0. The candidate still layers CUDA 12.8 Torch wheels over a CUDA 12.3.2/
cuDNN 9 base and is not a reproducible promoted production image.

The Worker token loaded `pyannote/speaker-diarization-community-1` through
`Pipeline.from_pretrained(..., token=...)`. The engine now handles both the
Pyannote 3 annotation and the Pyannote 4 `output.speaker_diarization` form.
Real GPU inference reported `cuda:0`; the isolated short probe returned 2
speakers/12 segments with 1,630 MB peak PyTorch VRAM allocation. Combined
large-v3 CUDA/FP16 processing passed on the six P1-C AMI fixtures and on the
P1-B/P1-C PT-BR fixture.

| AMI fixture | Baseline automatic DER | Candidate automatic DER | Baseline → candidate automatic speakers |
|---|---:|---:|---|
| clean 2-speaker | 22.639% | 18.769% | 3 → 2 (reference 2) |
| unequal volume | 36.813% | 35.358% | 3 → 2 (reference 2) |
| rapid turns | 15.207% | 14.939% | 3 → 3 (reference 4) |
| overlap | 18.698% | 13.818% | 3 → 4 (reference 4) |
| far-field noise | 33.718% | 16.905% | 2 → 4 (reference 4) |
| four speakers | 12.079% | 12.506% | 2 → 2 (reference 4) |

Automatic mode is the current Worker path. The benchmark's diagnostic
`known_num_speakers` mode is **not** exposed through the Worker, but regressed
materially: rapid turns DER 15.207% → 21.862%, and four speakers 10.707% →
24.609%. These changes need a quality decision and root-cause analysis before
Pyannote 4 promotion; they were not dismissed just because the automatic path
improved. The complete candidate measurements (including missed speech,
overlap, timestamps and resources) are in the ignored
`benchmarks/results/diarization/p2c1-community1-candidate.json`.

On the PT-BR two-speaker fixture, baseline and candidate both had WER/CER
**0/0**, 2 speakers, 12 segments and 84 words. Segment start/end timestamps
were identical; speaker labels were globally permuted while the speaker
partition remained identical. The candidate's one-run RTF was 0.277122 versus
0.212694 baseline; RAM peak 3,130 versus 3,143 MB. The GPU-total VRAM sampler
saw 11,478 MB peak versus 7,668 MB baseline, but candidate start occupancy was
5,607 MB versus 2,164 MB because the stable Worker was concurrently resident;
the totals are not process-private and cannot establish a VRAM regression or
safe single-Worker headroom. Docker's reported RAM total also differed by
0.01 MB, so the strict comparison CLI refused a direct hardware match.

Three consecutive **full combined** candidate jobs completed in one process,
with one Whisper model and one Pyannote pipeline reused: 17.515, 9.722 and
9.529 seconds; RAM at end 2,334, 2,373 and 2,373 MB. CPU/INT8 combined
processing also completed with 2 speakers/12 segments, but took 141.556
seconds for 62.54 seconds of audio (RTF 2.263, RAM peak 4,240 MB). This is
functional fallback, not a CPU performance endorsement. Whisper-only P1-B
quality results from the earlier snapshot remain unchanged.

`pip check` and imports passed. Installed-wheel `pip-audit` reported zero
findings **only while explicitly skipping** Torch, Torchaudio and Torchvision
`+cu128` wheels as unavailable on PyPI. The normalized version audit found
`PYSEC-2026-139` (local malicious PT2 artifact loading; no fix listed) and
`PYSEC-2025-194` (`torch.jit.script`; scanner says fix 2.13.0, while the
advisory text/range names 2.6.0). The Worker has no client-supplied model or
PT2/JIT execution endpoint, but model-source/cache compromise is not ruled
out. These are **not** declared fixed. The 23 stable scan entries and their
individual exposure/mitigation notes remain in the advisory table below.
Primary references: [RQ worker lifecycle](https://python-rq.org/docs/workers/),
[PyTorch CUDA fork limitation](https://docs.pytorch.org/docs/stable/notes/multiprocessing.html),
[Pyannote Community-1 interface](https://github.com/pyannote/pyannote-audio),
[PYSEC-2026-139](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2026-139.yaml),
[PYSEC-2025-194](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-194.yaml).

**ML promotion decision: rejected/deferred.** The automatic-mode gains and
PT-BR equivalence are encouraging, but the known-count DER regressions and
uncontrolled simultaneous-Worker VRAM/performance comparison leave the
joint quality/resource gate unresolved. No Faster-Whisper or stable ML package
version was changed to make scanner numbers look better.

### Operational Worker defect discovered and fixed independently of ML upgrade

The initial real HTTP job in `p2c` moved `queued → processing` but hung during
Faster-Whisper GPU inference. RQ's default `Worker` forked *after* engines/CUDA
had been initialized in the parent; after four minutes RQ killed the child
and moved its RQ record to `FailedJobRegistry` while the database remained
`processing`. This is the documented CUDA poison-fork hazard, which mocked
integration tests had not exercised.

`run_worker.py` now uses RQ `SimpleWorker`, which runs jobs in the preloaded
process without forking and reuses its engines. A runtime-only candidate was
built over the unchanged stable ML matrix. After confirming zero active RQ
jobs, the old Worker was stopped; startup recovery reenqueued the stranded
synthetic job; the candidate completed it. A real HTTP smoke then verified
login/session 200, recovered job/result 200, non-empty segments, delete 200,
subsequent GET 404, and login rate limit 429. The synthetic user/job were
removed and development DB counts returned to zero. The runtime fix alone
was then promoted to the Compose-managed `p2c-worker`, retaining Torch 2.2.2
and Pyannote 3.3.2. The previous Worker image is tagged
`p2c-worker:pre-simpleworker` for rollback. RQ `SimpleWorker` does not emit
periodic job heartbeats; monitor durable DB status and supervise/restart the
process. This is a deliberate operational trade-off, not a general-purpose
RQ worker recommendation.

A separate configuration fix sets Pydantic to hide input values in validation
errors. It closed a discovered path where a missing `DATABASE_URL` could show
part of `HF_TOKEN` in a traceback. The API image was rebuilt with this fix and
retained its ML-free import boundary; the old API image is tagged
`p2c-api:pre-settings-redaction`.

### Final validation and remaining gates

- Stable ML Worker and Pyannote 4 candidate: **101 backend tests passed** each
  against the isolated PostgreSQL/Redis/RQ test database, with no skips.
  These include new Pyannote contract, Worker no-fork and secret-error tests.
- Synthetic restore verification passed again (counts, JSONB, FKs, ownership,
  audit events, Alembic revision). `alembic check` found no pending operations
  in the isolated test database. No production backup/restore was attempted.
- Stable development stack after promotion: API, PostgreSQL, Redis and one
  Compose-managed Worker healthy; the Worker reports `SimpleWorker`, Torch
  2.2.2 and Pyannote 3.3.2. The stable stack's health reports diarization
  unconfigured, so its HTTP smoke validates the Whisper job path, not
  Pyannote. Pyannote 4 was exercised separately in the candidate image.
- `pip check` passed in both rebuilt stable API and Worker images. Importing
  `src.main` in the running API image did not import Torch, Pyannote or
  Transformers.
- Frontend: 9 Vitest tests, lint, build and `npm audit` (zero findings)
  passed. The in-app browser tool failed before session creation with missing
  `sandboxPolicy`; therefore **no visual walkthrough, console or browser
  network verification** is claimed.
- Python compilation, `git diff --check`, Compose config and API import without
  Torch/Pyannote passed. Remaining warnings are dependency deprecations.

Remaining release gates: locate and authorize the **actual** application
database, make and validate its backup, then audit ownership; resolve the
Pyannote 4 diagnostic regressions/resource comparison and decide residual
advisory risk; run a real browser walkthrough when the tool is functional.
Verdict: **P2-C AINDA NÃO CONCLUÍDA**.

---

## Earlier P2-C.1 snapshot (historical evidence, superseded where noted above)

Validation date: 2026-09-24. Scope: the existing P2-C implementation was not
reworked. The stable Worker image and `requirements.txt` remain unchanged.

## 1. ML/CUDA candidate and decision

The stable image is `p2c-worker` (Torch/Torchaudio 2.2.2,
Torchvision 0.17.2, Pyannote.audio 3.3.2/core 5.0.0,
Faster-Whisper 1.2.1, CTranslate2 4.8.2, CUDA 12.3.2/cuDNN 9).
`Dockerfile.worker.candidate` builds a separate `p2c1-worker-candidate`
layer over that image; it does not change the stable tag. The candidate has
Torch/Torchaudio 2.10.0+cu128, Torchvision 0.25.0+cu128,
TorchCodec 0.10.0, Pyannote.audio 4.0.7/core 6.0.1, NumPy 2.2.6;
Faster-Whisper and CTranslate2 remain at 1.2.1/4.8.2. Its base image still
provides CUDA 12.3.2/cuDNN 9 while PyTorch's wheels bundle CUDA 12.8
libraries. This mixed runtime is experimental, not a release recommendation.

The PyTorch project pairs the 2.10.0/0.25.0/2.10.0 domain triplet. TorchCodec
documents 0.10 with Torch 2.10. Pyannote 4 requires Torch/Torchaudio >=2.8 and
core >=6. Faster-Whisper documents CUDA 12 plus cuDNN 9 for current
CTranslate2. Sources: [PyTorch version matrix](https://github.com/pytorch/pytorch/wiki/PyTorch-Versions),
[TorchCodec compatibility](https://github.com/meta-pytorch/torchcodec#compatibility-with-torch-versions),
[Pyannote dependencies](https://github.com/pyannote/pyannote-audio/blob/main/pyproject.toml),
[Faster-Whisper GPU requirements](https://github.com/SYSTRAN/faster-whisper#gpu).

Candidate build, `pip check`, imports, and `torch.cuda.is_available()` passed
on RTX 3060. However, the current engine's `use_auth_token` keyword is rejected
by Pyannote 4. An isolated probe using the new `token` keyword failed with
403 on `pyannote/speaker-diarization-community-1` even when loading the old
3.1 repository. The locally configured token has no access to that new gated
model. The candidate therefore **fails the combined pipeline gate** and was
**not promoted**. Do not claim Pyannote 4 GPU, combined quality, combined
timestamps, or combined three-job stability were validated.

The smallest next change is to accept the Community-1 repository conditions
for the configured Hugging Face account, then adapt only the Pyannote engine's
loading keyword and output extraction in a disposable candidate. Repeat the
P1-C diarization fixtures and full pipeline before considering promotion.
The new model is not assumed quality-equivalent to 3.1.

## 2. Scanner findings: 23 entries, 20 distinct IDs

Reproduced with `pip-audit 2.10.1` against the stable Worker image. Three
IDs appear twice (`PYSEC-2025-41`, `PYSEC-2025-191`, `PYSEC-2026-1970`).
Descriptions for many entries explicitly cite Torch 2.6, 2.7, 2.8 or 2.10
while the advisory range still makes the scanner report 2.2.2. This is a
metadata/applicability uncertainty, **not** proof that these entries are fixed
or exploitable in 2.2.2. `fix` below is the scanner's fix version; `none`
means it provided none. All findings are on the Worker, not the ML-free API.

Mitigation codes used in each row:

- **A:** Worker isolated from HTTP; uploads require authentication; clients
  cannot submit checkpoint files or model graphs through the official API.
  Models come from configured gated repositories, but revisions are not pinned
  to immutable commits. Compromise of those artifacts remains possible.
- **B:** No direct invocation of the named Torch primitive in project code;
  no general tensor/graph execution API. Indirect use by dependencies has not
  been exhaustively proven absent.
- **C:** Distributed RemoteModule, Inductor compilation and profiler are not
  used by the application processing path.

| # | Advisory / alias | Description, affected version stated, scanner fix | Exploit precondition | Worker exposure; mitigation | Residual risk |
|---:|---|---|---|---|---|
| 1 | [PYSEC-2025-191](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-191.yaml) / CVE-2025-2953 | `mkldnn_max_pool2d` local DoS in 2.6.0+cu124; fix 2.7.1rc1 | Local call with crafted input | No direct call; B, C; 2.2.2 not named | Applicability unproven |
| 2 | [PYSEC-2026-1970](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2026-1970.yaml) / CVE-2025-3730 | `ctc_loss` local DoS in 2.6.0; fix 2.8.0 | Local malformed CTC operation | No direct call; B; 2.2.2 not named | Applicability unproven |
| 3 | [PYSEC-2025-41](https://github.com/advisories/GHSA-53q9-r3pm-6pq6) / CVE-2025-32434 | `torch.load(weights_only=True)` RCE; <2.6.0, fix 2.6.0 | Load malicious checkpoint | Pyannote loads model artifacts, not uploaded checkpoints; A | Conditional high if model source/cache compromised |
| 4 | PYSEC-2025-41, duplicate | Same RCE and range as #3; fix 2.6.0 | Same as #3 | Same as #3; A | Same as #3, not a second flaw |
| 5 | [PYSEC-2024-259](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2024-259.yaml) / CVE-2024-48063 | Distributed `RemoteModule` deserialization RCE; <=2.4.1, fix 2.5.0; disputed intended behavior | Run distributed RemoteModule with malicious peer | Not used; A, C | Low on current route; distributed use would reopen |
| 6 | [PYSEC-2025-205](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-205.yaml) / CVE-2025-55553 | `proxy_tensor.py` syntax/DoS in 2.7.0; fix 2.7.1 | Compile affected graph | No compiler path; B, C; 2.2.2 not named | Applicability unproven |
| 7 | [PYSEC-2025-206](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-206.yaml) / CVE-2025-55554 | `nan_to_num().long()` integer overflow in 2.8.0; fix 2.9.0 | Call affected conversion | No direct call; B; 2.2.2 not named | Applicability unproven |
| 8 | [PYSEC-2025-207](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-207.yaml) / CVE-2025-55557 | `cummin` under Inductor DoS in 2.7.0; fix 2.7.1 | Compile affected graph | No compiler path; B, C; 2.2.2 not named | Applicability unproven |
| 9 | [PYSEC-2025-204](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-204.yaml) / CVE-2025-55552 | `rot90` + `randn_like` wrong behavior in 2.8.0; fix 2.9.0 | Call both operations | No direct call; B; 2.2.2 not named | Applicability unproven |
| 10 | [PYSEC-2026-139](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2026-139.yaml) / CVE-2026-4538 | PT2 loading deserialization in 2.10.0; fix none | Load malicious PT2 artifact | Not on 2.2.2 route; A, C | Candidate 2.10 still flagged; no proven fix |
| 11 | [PYSEC-2025-209](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-209.yaml) / CVE-2025-55560 | Sparse conversion under Inductor DoS in 2.7.0; fix 2.7.1 | Compile affected graph | No compiler path; B, C; 2.2.2 not named | Applicability unproven |
| 12 | [PYSEC-2025-208](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-208.yaml) / CVE-2025-55558 | Conv2d/hardshrink/view-mv under Inductor buffer overflow in 2.7.0; fix 2.7.1 | Compile affected graph | No compiler path; B, C; 2.2.2 not named | Applicability unproven |
| 13 | PYSEC-2025-191, duplicate | Same primitive/version as #1, but this scanner record supplies no fix | Same as #1 | Same as #1; B, C | Conflicting fix metadata; no second flaw |
| 14 | [PYSEC-2025-198](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-198.yaml) / CVE-2025-46148 | Eager `PairwiseDistance(p=2)` incorrect result through 2.6.0; fix 2.7.0 | Use affected distance operation | No direct call; possible indirect embedding use not excluded; B | Unquantified output-integrity risk |
| 15 | [PYSEC-2025-203](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-203.yaml) / CVE-2025-55551 | `linalg.lu` slicing DoS in 2.8.0; fix 2.9.0 | Slice affected LU result | No direct call; B; 2.2.2 not named | Applicability unproven |
| 16 | [PYSEC-2025-189](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-189.yaml) / CVE-2025-2148 | Profiler tuple callback memory corruption in 2.6.0+cu124; fix none | Invoke profiler callback with crafted argument | No profiler path; B, C; 2.2.2 not named | Applicability unproven |
| 17 | [PYSEC-2025-190](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-190.yaml) / CVE-2025-2149 | Quantized sigmoid improper initialization in 2.6.0+cu124; fix none | Invoke quantized sigmoid with crafted scale/zero point | No direct call; B; 2.2.2 not named | Applicability unproven |
| 18 | [PYSEC-2025-192](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-192.yaml) / CVE-2025-2998 | `pad_packed_sequence` memory corruption in 2.6.0; fix none | Local crafted packed sequence | No direct call; B; 2.2.2 not named | Applicability unproven |
| 19 | [PYSEC-2025-193](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-193.yaml) / CVE-2025-2999 | `unpack_sequence` memory corruption in 2.6.0; fix 2.9.1 | Local crafted sequence | No direct call; B; 2.2.2 not named | Applicability unproven |
| 20 | [PYSEC-2025-194](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-194.yaml) / CVE-2025-3000 | `torch.jit.script` memory corruption; text names 2.6.0, scanner fix 2.13.0 | Script crafted model/code locally | No direct JIT path; B, C | Range/text disagree; still flagged on candidate 2.10 |
| 21 | [PYSEC-2025-195](https://github.com/pypa/advisory-database/blob/main/vulns/torch/PYSEC-2025-195.yaml) / CVE-2025-3001 | `lstm_cell` memory corruption in 2.6.0; fix 2.10.0 | Local crafted LSTM inputs | No direct call; B; 2.2.2 not named | Applicability unproven |
| 22 | PYSEC-2026-1970, duplicate | Same CTC DoS and fix as #2 | Same as #2 | Same as #2; B | Same as #2, not a second flaw |
| 23 | [PYSEC-2026-2286](https://github.com/advisories/GHSA-63cw-57p8-fm3p) / CVE-2026-24747 | `weights_only` unpickler memory corruption/RCE; <2.10.0, fix 2.10.0 | Load malicious `.pth` checkpoint | Pyannote model artifacts are loaded from configured repo/cache, not client upload; A | Conditional high if model source/cache compromised |

`pip-audit` on the candidate's installed CUDA wheels said "zero" but skipped
Torch, Torchaudio and Torchvision because their `+cu128` local versions were
not found on PyPI. Auditing normalized public versions from
`requirements.worker.candidate.audit.txt` found **two** Torch entries:
`PYSEC-2026-139` (no fix given) and `PYSEC-2025-194` (scanner fix 2.13.0).
Therefore **zero findings is not an acceptable security claim** for the
candidate. The scanner's applicability/range metadata still needs upstream
triage; no advisory has been declared fixed merely from a skipped audit.

## 3. Benchmark comparison

| Check | Stable P2-C | Candidate | Decision |
|---|---:|---:|---|
| PT-BR large-v3 CUDA/FP16 WER / CER | 0.051471 / 0.008333 | 0.051471 / 0.008333 | Same fixture hash and quality |
| Whisper-only segment timestamp | 0.00–77.68 s | 0.00–77.68 s | Same, without diarization |
| PT-BR CUDA RTF / peak RAM | 0.074024 / 3149 MB | 0.072484 / 3162 MB | Comparable single run |
| CUDA peak VRAM delta (GPU-total sampler) | 4121 MB | 4111 MB | Comparable; absolute start differed due other GPU users |
| CPU/INT8 RTF / peak RAM | 0.511570 / 3071 MB | 0.549133 / 3066 MB | Ran; time difference not yet a regression conclusion |
| Three sequential Whisper-only jobs | Stable combined baseline reused engines | Candidate RTF 0.086604 / 0.059861 / 0.062747, one engine, end RAM ~1797 MB | Whisper-only passed |
| Pyannote GPU / combined speakers and timestamps | 2 speakers, 12 segments, 84 words | Blocked by API mismatch and model 403 | **Not homologated** |

Benchmark JSON files are in ignored `benchmarks/results/p2c1-candidate-*.json`.
The GPU sampler measures total device usage, not this container's private
allocation. Neither one-run timings nor total VRAM values justify a strong
performance conclusion.

## 4. Ownership and restore drill

Docker labels and mount names identified `p2c_postgres_data` and the new
`p2c1drill_postgres_data` as project test volumes. The pre-existing
`backend_postgres_data` is not an authorized project target and was not
used in this phase. No production database was supplied. The read-only
`p2c` ownership audit returned zero rows; the synthetic `p2c1drill` audit
returned total 2, user_id 0, owner_sub 2, exact matches 1, unknown rows 1,
unknown subjects 1, duplicate usernames 0, conflicting matches 0, orphan
user/transcription references 0. The CLI exits 1 because unresolved rows
remain. The report never prints legacy subjects unless explicitly requested.

`scripts.report_unresolved_ownership` now reports those counts and refuses
backfill if duplicate usernames exist. The SQLite regression test verifies
exact-only backfill, preservation of unknown rows and conflict detection.
No Alembic drop of `owner_sub` was created: the real deployment is not
identified or backed up, and the synthetic fixture is deliberately unresolved.

For the restore drill, a new isolated Compose project `p2c1drill` was created.
After Alembic upgrade, `tests/fixtures/p2c1_restore_seed.sql` inserted
synthetic users, transcriptions, jobs, ownership and audit metadata.
`pg_dump -Fc` from `transcription_db` was restored with `pg_restore
--exit-on-error` into the new `transcription_restore_p2c1` database (no
`--clean`, no overwrite). `p2c1_restore_verify.sql` passed on source and
target: users 2, transcriptions 2, jobs 2, owners 2, audit events 1,
JSONB transcript/metadata preserved, four FKs present, zero orphan job/owner
references, ownership subjects unchanged, Alembic `20260920_0002`.
This is a **local isolated synthetic drill**, not a production restore.
The `p2c1drill` PostgreSQL/Redis containers and React dev server were stopped
after validation; isolated volumes and the candidate image were retained for
inspection. The pre-existing `p2c` stack was left running.

## 5. Frontend and final validation

The existing `p2c` API/Worker/PostgreSQL/Redis stack returned HTTP 200 and
`/health` reported one RQ Worker. The React dev server returned HTTP 200 on
127.0.0.1:3000. The in-app browser could not connect in this session; no
visual interaction, console inspection or browser network inspection is
claimed. Automated regression coverage was extended for deletion and the
rate-limit upload error; the delete button acquired an accessible name.

- Stable Worker test image in isolated project: **95 passed, 0 skipped**,
  including PostgreSQL/Redis/RQ; 7 deprecation warnings.
- Alembic on a new empty test database: upgrade, downgrade one revision,
  re-upgrade, check all passed. Source/restore databases were not downgraded.
- Candidate image built; `pip check` and imports/CUDA passed. Its ML
  homologation failed as described above; no full candidate suite/promotion.
- API and stable Worker Docker builds passed; API import had neither Torch nor
  Pyannote in `sys.modules`.
- `pip check` passed in API, stable Worker and candidate. `pip-audit` found
  zero in API, 23 raw entries in stable Worker, and two normalized Torch
  entries in the candidate; the installed CUDA wheels were skipped.
- Frontend: 9 Vitest tests, lint, build and full/production `npm audit`
  passed (0 findings).
- Compose config with test and maintenance profiles, Python compilation and
  `git diff --check` passed. Git emitted only CRLF/LF conversion warnings.

## Release gates still open

1. Authoritative deployment database identification, read-only ownership
   audit, backup and restore drill before any production migration.
2. Hugging Face Community-1 access for the configured token, minimal
   Pyannote 4 adapter, full GPU diarization/combined pipeline/timestamps and
   three combined jobs compared with P1-C.
3. Resolve or explicitly accept remaining scanner findings for the chosen
   tested ML matrix. A skipped CUDA wheel audit is not a clean audit.
4. Browser walkthrough when the in-app browser is available; automated tests
   cover the current fallback but do not replace visual/network inspection.

Verdict: **P2-C AINDA NÃO CONCLUÍDA**.
