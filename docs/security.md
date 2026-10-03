# Segurança, privacidade e riscos conhecidos

## Controles atuais

Login valida users persistentes/bcrypt (cost 12), não uma sessão anônima de demo.
Admin pode ser provisionado no primeiro login configurado. Senhas maiores que
72 bytes são rejeitadas, não truncadas. CLI create_local_user usa getpass.

JWT HMAC SHA-2 exige sub, exp, iat, issuer, audience e jti; sub novo é users.id.
Username-sub legado exige correspondência exata a usuário persistente ativo.
Ownership de contas usa user_id; Guest usa guest_session_id e prova assinada temporária. owner_sub permanece apenas como ponte inequívoca para dados legados.
Acesso cruzado/não resolvido retorna 404. Flags legadas não tornam rotas privadas
anônimas. Production rejeita placeholders/chave curta, demo e CORS wildcard.

API trata upload como não confiável: tamanho, extensão allow-list, magic bytes,
conteúdo não vazio e filename opaco. FFmpeg pertence ao Worker.
Respostas têm nosniff, frame denial, no-referrer, permissions-policy e no-store
para dados sensíveis. CORS é allow-list, sem credenciais por padrão.
TLS/HSTS/proxy confiável, limite de request no perímetro e rotação de logs
continuam responsabilidades de implantação.

## Rate limiting Redis e secrets

Cadastro público não provisiona admin nem assume ownership legado por username.
Sessões Guest têm prova/expiração server-side e rotas próprias; rotas privadas
não foram desprotegidas. Guest AssemblyAI exige opt-in explícito, chave somente
no Worker e reserva financeira cumulativa no PostgreSQL, desligados por padrão.
Não há fallback local nem repetição automática de submissão em recovery.
Quotas de Guest/contas públicas não equivalem a orçamento financeiro;
contas públicas não recebem acesso à chave platform. BYOK cifra chaves próprias
com envelope Fernet ligado ao usuário/provider; respostas têm apenas metadados,
referências nos jobs não contêm secrets e revogação não faz fallback. Ver
[proteção e implantação BYOK](provider_preferences.md) e
[políticas de Guest/contas](guest_and_accounts.md) para limites, cleanup e contexto
de identidades locais provisionadas explicitamente pelo operador.
Ver [AssemblyAI](assemblyai.md) para teto financeiro, resultados locais e gates
de retenção/consentimento do provider antes de oferecer Guest público. Exclusão
local não executa exclusão remota nem garante o TTL dos artefatos externos.

Buckets atômicos de janela fixa: login IP 30 e conta 10 por 5 min; upload IP 300
e criação de job por usuário 30 por hora. Configuráveis. IP compartilhado precisa
dimensionamento pelo operador. Não confiar em forwarded headers não validados.
429 tem Retry-After. Falha Redis em login/upload/job retorna 503 sem autenticar/
salvar upload; consultas de resultados já persistidos não dependem do provider.

Compose separa segredos: API recebe JWT/admin; Worker HF/AssemblyAI/Gemini;
API/Worker compartilham somente a chave independente de criptografia BYOK;
migrate/maintenance apenas conexão de banco. Flags *_CONFIGURED não são chaves.
Cache de modelos só no Worker. .env/dados/results/cache/archive ficam fora de build.
Não logar transcript, minutos, originais/paths, email, hashes de senha, bearer
ou credentials. Filtro/formatter redige assignments, tokens e senhas de URLs.

## Privacidade e manutenção

Originais/WAVs são eliminados após processamento, com proteção de jobs ativos
e reconciliação idempotente em falha. Retenção de transcrições/audit é indefinida
por padrão; preview explícito antes de --apply. Dados exportados incluem Meeting/
Intelligence e versões; não incluem hashes, secrets ou input paths.
Erasure cascade preserva eventos com actor SET NULL. Audit é append-only no
nível da aplicação, não ledger criptográfico; admins/retention podem remover.

Provider local não envia runtime áudio a nuvem. HF recebe requests de aquisição
de modelos/token. AssemblyAI recebe áudio somente por seleção explícita;
Gemini recebe transcript/contexto somente por solicitação explícita.
Não existe fallback silencioso local → cloud.

## Auditoria registrada e dívida

A validação de 2026-10-02 antes desta revisão de higiene registrou pip check
limpo, pip-audit API **1** e Worker **24** (PyJWT + 23 entradas Torch).
npm audit do frontend atual retornou zero; o push também reportou 29 alertas
Dependabot na branch padrão remota, não uma auditoria da branch de trabalho.
Não declarar essas vulnerabilidades corrigidas pela remoção de arquivos.

PyJWT 2.14.0: PYSEC-2026-4141 / GHSA-42vr-xj54-vc7v, correção indicada 2.15.0.
[Advisory do mantenedor](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-42vr-xj54-vc7v)
descreve payload JSON profundamente aninhado em parsing sem assinatura.
A aplicação não usa PyJWKClient nem verify_signature=False; exige assinatura
HMAC com algoritmo explícito antes de payload parsing. Um teste rejeita payload
forjado de 20000 níveis com 401. Isso mitiga exposição desta rota; não corrige a
biblioteca. Upgrade pontual com testes permanece backlog, não executado aqui.

A tabela abaixo preserva a triagem histórica Torch (23 entradas, 20 IDs,
duplicações/metadata conflitante explícitas). Não é nova análise de exploração
nem declaração de correção; validar a matriz conjuntamente antes de atualizar.

## Triagem histórica Torch: 23 entradas, 20 IDs

Reproduced with `pip-audit 2.10.1` against the stable Worker image. Three
IDs appear twice (`PYSEC-2025-41`, `PYSEC-2025-191`, `PYSEC-2026-1970`).
Descriptions for many entries explicitly cite Torch 2.6, 2.7, 2.8 or 2.10
while the advisory range still makes the scanner report 2.2.2. This is a
metadata/applicability uncertainty, **not** proof that these entries are fixed
or exploitable in 2.2.2. `fix` below is the scanner's fix version; `none`
means it provided none. All findings are on the Worker, not the ML-free API.

Mitigation codes used in each row:

- **A:** Worker isolated from HTTP; uploads require a user or signed Guest identity;
  public local processing has shared quotas, size, duration and timeout limits; clients
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
the archived `requirements.worker.candidate.audit.txt` found **two** Torch entries:
`PYSEC-2026-139` (no fix given) and `PYSEC-2025-194` (scanner fix 2.13.0).
Therefore **zero findings is not an acceptable security claim** for the
candidate. The scanner's applicability/range metadata still needs upstream
triage; no advisory has been declared fixed merely from a skipped audit.

## Gates restantes

Modelos/cache devem ter origem confiável; revisões ainda não são fixadas a commits
imutáveis. Upload não aceita checkpoints/graphs, mas comprometimento da origem/
cache permanece risco. Wheels CUDA omitidos pelo scanner não significam segurança.
Gemini SDK legado, runtime e warnings exigem atualização futura coordenada.
Não há homologação de produção. Ver [matriz e gates](ml_validation.md).
