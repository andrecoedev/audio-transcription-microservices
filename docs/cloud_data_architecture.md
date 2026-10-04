# Arquitetura de dados Cloud e Local

## Auditoria antes da P5-04

O PostgreSQL é a fonte de verdade do domínio. Firebase autentica e vincula
identidades externas a `users.id`; não substitui o domínio. Redis/RQ coordena
execução, não armazena o único exemplar de resultados. Não há justificativa para
Firestore nesta arquitetura.

| Categoria | Armazenamento atual | Duração / exclusão | Ownership e acesso | Adequação SaaS |
|---|---|---|---|---|
| Usuários | PostgreSQL `users`, senha bcrypt quando local | Até erasure; filhos cascade, audit actor SET NULL | Identidade interna; auth/operador | Preservar |
| Firebase | `firebase_identities`, mapping projeto/UID → User | Até exclusão do User; conta Firebase é externa | Apenas identidade verificada; sem linking automático por e-mail | Preservar |
| Upload original | Volume filesystem compartilhado, `AUDIO_UPLOAD_DIRECTORY`; path absoluto em job | Worker tenta excluir após sucesso/falha; reconciliation por idade | Sem rota pública; owner pelo Transcription, filename UUID | Path absoluto acopla instâncias ao mesmo mount |
| WAV/temporários | Diretório `temp` no Worker | `finally` do pipeline; crash exige limpeza operacional | Worker apenas | Efêmero local é adequado; não distribuir como dado durável |
| Transcrição/segmentos | `transcriptions`, segmentos JSONB | Retenção configurável; zero = indefinida; DELETE cascade | `transcription_owners`: User ou Guest; API verifica owner/scopes | Preservar |
| Reuniões | `meetings`, relação 1:1 com Transcription | Cascade da transcrição; DELETE de reunião apaga agregado | Ownership via transcrição | Preservar |
| Falantes | Speaker IDs nos segmentos; nomes em `meeting_speakers` | Cascade Meeting | Mesmo owner; nomes editáveis, sem duplicar transcript | Preservar |
| Resumo inteligente | Revisões `meeting_intelligence`, resultado/evidência JSONB | Revisões persistem, independentes do RQ; cascade Meeting | Owner/scopes; provider externo recebe contexto por ação explícita | Preservar |
| Tarefas | `meeting_actions` e revisões/disposições | Cascade Meeting; independentes de regeneração AI | Owner do agregado | Preservar |
| Preferências | `user_provider_preferences` | Até exclusão do User | Isolamento por User | Preservar |
| BYOK | `user_provider_credentials`, envelope Fernet ligado a User/provider | Substituição/remoção explícita; cascade User | API write-only; decrypt interno pelo Worker; metadata segura | Preservar; chave de cifra exige gestão/backup separados |
| Jobs | `transcription_jobs`, opções/proveniência/estado em PostgreSQL | Até cascade do agregado; ledger financeiro mantém guard no-repeat | Mesma transcrição; paths/secrets não saem em resultado | Estado durável adequado; referência de áudio precisa desacoplamento |
| Transitórios | Redis/RQ registries/queue e sessão SDK/frontend | TTL/processo; recovery lê banco | Sem credenciais BYOK nas mensagens | Não usar como fonte de verdade |
| Guest | `guest_sessions` e ownership temporário no PostgreSQL | TTL configurável; manutenção preserva jobs ativos | Proof separado em sessionStorage da aba; claim explícito | Preservar políticas e orçamento externo |
| Exports | JSON de privacidade sob demanda; export frontend por download | Sem catálogo/objeto durável de export atualmente | Dados autorizados; sem hashes, credenciais ou paths internos | Não criar persistência desnecessária |
| Auditoria/ledger | `audit_events`, platform reservations/calls | Audit TTL separado; ledger pode sobreviver ao recurso para no-repeat | Operação interna, eventos mínimos sem transcript | Documentar finalidade e retenção na implantação |

Evidências principais: `src/models.py`, `src/authorization.py`, routers
`transcriptions`, `meetings`, `meeting_intelligence`, serviços
`provider_credentials`, `privacy`, `guest_retention`, `storage_lifecycle` e Worker.
Export/erasure de privacidade são serviços internos/testados, não novos endpoints
de produto. Esta Task não amplia essa superfície.

## Decisões e plano P5-04

1. Preservar PostgreSQL, constraints, migrations, contratos HTTP e `users.id`.
2. Introduzir uma interface pequena de Object Storage; a aplicação não importa
   SDK de vendor. O adapter local é necessário para desenvolvimento/testes.
3. Novos uploads deverão guardar referência opaca de objeto, não caminho físico.
   O nome original serve só como metadado sanitizado. Jobs antigos precisam de
   leitura compatível explícita; não reescrever registros sem inventário/backup.
4. FFmpeg continua recebendo um arquivo local materializado pelo Worker. Local
   pode reutilizar o arquivo sem cópia; futuro adapter remoto materializa em
   diretório efêmero e remove em `finally`. Não alterar ML/processamento nesta Task.
5. Exclusão de banco e storage não é transação distribuída. Registrar intenção
   durável de cleanup no mesmo commit que remove o agregado; falha de storage
   mantém retry observável/idempotente, sem depender do Redis. Proteger jobs ativos.

## Lifecycle e limites de implantação

Upload validado (extensão, assinatura, tamanho, limites/contexto) → objeto privado
→ referência/ownership/job PostgreSQL → RQ → Worker/materialização → resultado
PostgreSQL → remoção do original/temporários → retenção/exclusão do agregado.
Resultados concluídos continuam disponíveis após perda de Redis. Áudio não tem
endpoint público nem URL assinada nesta Task; ownership autoriza o domínio, não
conhecimento de uma chave de objeto.

Cloud e Local usam configuração/adapters, não `if cloud` espalhado. O adapter
local exige o mesmo volume/raiz entre API, Worker e manutenção; sozinho não resolve
múltiplos hosts. USAGI Cloud ainda precisará de adapter remoto privado, IAM mínimo,
TLS, gestão de secrets, lifecycle do bucket, backup/restore PostgreSQL, scheduler
de manutenção e homologação real de falhas. Não declarar SaaS/produção homologado
com base no backend local ou em mocks. Não tornar objetos públicos por conveniência.

## Implementação da P5-04

`ObjectStorage` define put/open/delete/exists/metadata/materialize. O adapter
local publica atomicamente objetos sob UUID + extensão validada, rejeita traversal,
não sobrescreve objetos e não lê/materializa symlinks. Upload passa diretamente
pelo adapter, com validação de assinatura e contagem real dos bytes; não cria uma
segunda cópia persistente. Spool HTTP e WAV do pipeline continuam efêmeros.

Configuração: `OBJECT_STORAGE_BACKEND=local` e `AUDIO_UPLOAD_DIRECTORY` igual entre
API, Worker e manutenção. Só local está implementado; valor não suportado é erro,
não fallback. O Compose conserva `processing_data`. Não há SDK cloud novo, URLs
públicas, download de áudio ou endpoints novos de produto.

Migration aditiva `20261004_0011` preserva `input_path` dos jobs antigos, acrescenta
`input_object_key` nullable e `object_deletions`. Novos jobs usam key e caminho
legado vazio; não há backfill automático. Downgrade recusa chaves ou intenções
existentes: arquive/migre explicitamente antes de retirar essas colunas/tabela.

Cleanup é outbox transacional, sem FK para o agregado removido. É registrado no
commit terminal do Worker ou no commit que exclui dados. Falha de storage mantém
intenção/tentativas; crash após apagar e antes do commit é seguro porque delete é
idempotente. Falha de persistência terminal preserva input ativo para recovery.
Maintenance faz retry sem Redis. Consulte [operação](operations.md#retenção-e-reconciliação).

DELETE de reunião/transcrição remove o agregado e seus derivados estruturados
por cascade. Jobs queued/processing bloqueiam exclusão; erasure interna de usuário
também os bloqueia. RQ terminal pode expirar sem afetar resultados. Jobs de
intelligence sem agregado não produzem novos resultados; não são fonte de verdade.
Exports atuais são respostas/downloads, não objetos persistidos a apagar. Artefatos
temporários seguem `finally`; nenhum catálogo novo de exports foi criado.

Cloud continua pendente: adapter remoto privado, materialização efêmera segura,
permissões mínimas/IAM, TLS, provisionamento, lifecycle remoto e testes de falha
reais. A abstração prepara esse caminho, mas o volume local não resolve múltiplos
hosts. Esta Task não homologa infraestrutura de produção nem altera providers/ML.

## Validação local e pendências (2026-10-04)

Python 3.12 descartável com dependências HTTP fixadas: 293 testes passaram,
1 skip (symlink exige privilégio Windows) e 3 avisos de depreciação. Essa execução
excluiu explicitamente `tests/integration` e `test_diarization_filter.py`, que
precisa da stack ML. Incluiu testes de API isolation e mocks do Worker, não
inferência real. Frontend sem alteração funcional: 156 testes passaram, lint e
build passaram. Compilação Python, `git diff --check` e Compose config passaram.

O engine Docker Linux não estava acessível. Permanecem pendentes: suíte completa
Linux (incluindo symlink/ML), PostgreSQL/Redis/RQ reais, Alembic upgrade/downgrade/
check isolados, builds Docker e secret scanner/Security Gate final antes do PR.
Nenhuma migration foi aplicada ao banco de desenvolvimento real nesta execução;
nenhum banco/volume existente foi apagado. Esses resultados não autorizam promoção
para produção nem substituem a homologação pendente.
