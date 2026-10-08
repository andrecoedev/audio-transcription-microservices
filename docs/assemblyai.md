# AssemblyAI: admissão, execução e operação

## Contrato recuperado

O adapter anterior era parcialmente quebrado: perdia timestamps/falantes/status
e usava Pyannote com transcrição cloud por corte. Agora o Worker normaliza um WAV
mono, valida duração e envia uma única submissão AssemblyAI. Detecção usa
`speaker_labels`; utterances viram segmentos em segundos e speakers estáveis por
primeira ocorrência cronológica, preservando overlap. Sem detecção, texto e
limites das palavras formam um segmento. Silence sem conteúdo é resultado vazio;
resposta malformada falha, não fabrica texto. Tolerância de fim de segmento: 0,1s
para precisão de codec, com clamp; outros timestamps inválidos são rejeitados.

SDK `assemblyai==0.40.2` preservado. O escape hatch RawTranscriptionConfig fixa
somente `speech_models=["universal-2"]`, sem lista de fallback: nomes legados/default
podem mudar de modelo no servidor. Client tem chave própria, não altera settings
globais. Modelo solicitado é registrado como metadata; não é benchmark de qualidade
comparativo nem garantia de versão imutável do modelo hospedado.
API não importa SDK/ML; jobs cloud não inicializam Torch/CUDA/Whisper/Pyannote/Gemini.
Whisper/P3 mantêm contratos existentes. Automatic/Settings/BYOK são descritos em
[preferências por conta](provider_preferences.md); reservas abaixo são somente platform.

## Configuração (valores não secretos)

| Variável | Default | Uso |
|---|---:|---|
| AAI_PLATFORM_ENABLED | false | Permissão explícita para consumir a chave platform |
| AAI_GUEST_ENABLED | false | Legado; não habilita processamento Guest demonstrativo |
| AAI_PLATFORM_BUDGET_CENTS | 0 | Teto cumulativo USD, não diário/mensal |
| AAI_MAX_AUDIO_SECONDS | 600 | Máximo cloud, também para identidades locais |
| AAI_TIMEOUT_SECONDS | 180 | Deadline da submissão/polling |
| AAI_HTTP_TIMEOUT_SECONDS | 30 | Timeout por operação HTTP |
| AAI_POLL_INTERVAL_SECONDS | 3 | Intervalo das consultas |

Chave somente no Worker; API recebe AAI_API_KEY_CONFIGURED como booleano.
Presença da chave não autoriza consumo. Recrie API/Worker após alterar política.
Contas públicas autenticadas NÃO herdam credencial platform, mesmo com flags
ligadas; user credential ainda é explicitamente negada, nunca desviada para platform.
Guest agora é exclusivamente demonstrativo: novas chamadas AssemblyAI são negadas
independentemente de `AAI_GUEST_ENABLED`. Limites e retenção permanecem nos registros
anteriores; evidências de chamadas Guest abaixo são históricas, não autorização
para consumo novo. Consulte [contrato Guest atual](guest_and_accounts.md).
Seu timeout RQ default 300s é independente da duração do áudio. Deadline HTTP não
substitui supervisão RQ: upload em streaming pode consumir várias operações socket.

## Reserva cumulativa e recuperação

Migration 0008 cria platform_provider_budgets e platform_provider_calls. Não
modifica migrations anteriores. Reserva e job são persistidos na mesma transação.
UPDATE condicional serializa concorrência; teto efetivo é o menor entre o inicial
persistido e a configuração atual. Aumentar configuração NÃO aumenta o teto
persistido: exige decisão/ajuste operacional explícito, nunca apagar o ledger.

Reserva por job usa a duração máxima configurada, arredondada em centavos, a
US$1/h conservador, incluindo falantes. Default 600s reserva 17 centavos, mesmo para
áudio curto. Foi adotada margem sobre a tarifa pública revisada em 2026-10-02:
Universal-2 US$0,15/h + falantes US$0,02/h; cobrança descrita por segundo. Isso é
controle conservador de admissão, NÃO fatura ou consulta de saldo do provider.
Rever preços/contrato antes de habilitar ou se o provider os alterar. Não limita
consumo de outras aplicações que compartilhem a mesma chave.

Reserva nunca é devolvida automaticamente, mesmo antes de cobrança ou em falha.
Teto US$2 comporta no máximo 11 reservas de 17 centavos; falhas também podem consumi-las.
Antes de upload, Worker confirma marker `attempted` em transação curta. Tentativa
ambígua/crash/timeout NÃO reenvia POST em recovery. Registro sem reserva, cancelamento
da política ou tentativa já marcada falham com PostgreSQL/RQ consistentes. Esta é
uma escolha conservadora: perder uma tentativa custa disponibilidade, não cobrança
duplicada. Não há retomada automática por ID remoto nesta entrega. Em falha ambígua,
operador deve verificar a conta AssemblyAI e decidir nova execução autorizada; não
editar marker para repetir às cegas. Desligue política para suspender novas chamadas.

Claim não muda origem/contexto financeiros. Exclusão/retention mantém ledger e
totais, só remove referência ao transcript via SET NULL. Downgrade recusa registros
financeiros existentes. Não rodar suíte que trunca tabelas no banco de homologação
paga depois de criar reservas reais; integração usa apenas banco sintético autorizado.

## Privacidade e implantação

Exclusão/TTL USAGI controla armazenamento LOCAL. Não executa DELETE remoto nem
configura TTL/model-training na AssemblyAI nesta entrega. O provider documenta
retenção de artefatos que varia com contrato/TTL; transcript pode permanecer sem
TTL. Configure retenção/opt-out, aviso/consentimento de processamento externo e
procedimento de eliminação remota ANTES de oferecer Guest público. Não prometer
eliminação remota em 24h apenas por apagar resultado USAGI. Sem publicação/produção
homologada. Smokes usaram somente áudio público não sensível; não listar/exportar
outros transcripts da conta para investigação. Erros SDK são convertidos em
categorias seguras (credential/quota/timeout/invalid_response/unavailable), sem
secret, corpo de provider ou transcrição em logs/respostas.

## Evidência local

Dois jobs HTTP reais em usagip4auth, PostgreSQL 16/Redis 7/RQ supervisionado, com
teto TOTAL autorizado US$2 (não franquia pública renovável):

| Fixture pública FLEURS PT-BR | Áudio | Resultado | Tempo HTTP total |
|---|---:|---|---:|
| Trecho quality sem falantes | 8s | 1 segmento / 1 speaker | 6,083s |
| Fixture controlada duas vozes | 62,54s | 8 segmentos / 2 speakers | 10,453s |

Polling/completed, consulta após apagar RQ, signup/login, claim explícito,
Meeting e exclusão local passaram. Ledger sobreviveu: 34 centavos reservados,
2 markers attempted, referências null. Não equivale a US$0,34 faturado. Estimativa
pela tarifa pública, sem créditos/contrato: aproximadamente US$0,0033 total;
fatura real não consultada. Sem nova chamada para repetir erro. Primeira tentativa
HTTP sofreu 429 pela quota sintética anterior antes de criar job; usou-se namespace
Redis isolado novo, mesmos limites e mesmo PostgreSQL/ledger, sem reset financeiro.
Sem walkthrough visual nem WER/DER comparativo, inferência GPU ou homologação produção.

Fontes primárias: [preços](https://www.assemblyai.com/pricing),
[cobrança por segundo](https://support.assemblyai.com/articles/3853403741-how-does-pricing-work),
[changelog/model pinning](https://www.assemblyai.com/changelog?3b7e7275_page=3),
[falantes](https://www.assemblyai.com/docs/pre-recorded-audio/label-speakers),
[retenção](https://www.assemblyai.com/docs/data-retention-and-model-training),
[eliminação](https://www.assemblyai.com/docs/delete-transcripts).
