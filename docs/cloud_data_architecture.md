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

Status deste documento: auditoria e decisões pré-implementação; os resultados e
detalhes efetivamente implementados devem ser consolidados antes do PR.
