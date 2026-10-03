# Preferências e credenciais próprias de providers

## Contrato por conta

Configurações → Provedores salva preferências no PostgreSQL, não no JWT nem em
localStorage. Transcrição: `automatic`, `whisper`, `assemblyai`. Resumo inteligente:
`automatic`, `gemini`. Detecção de falantes tem default por conta e override por job.
Guest não acessa este contrato: continua AssemblyAI platform com política/orçamento
próprios e sem BYOK. Perfil visual antigo em Settings ainda é local; não confundir
preferências persistentes de providers com atualização de identidade.

`GET/PATCH /settings/providers` consulta/salva preferências e capabilities seguras.
`POST /settings/providers/{assemblyai|gemini}/credential` recebe `{secret: ...}`;
`DELETE` no mesmo caminho remove explicitamente. Auth obrigatória, sem parâmetro
user_id nem acesso especial de admin a chaves alheias. Respostas mostram apenas
configured/updated_at/origem, nunca segredo, prefixo, hash ou ciphertext. Validação
não ecoa request. Corpo POST/PATCH limitado a 16 KiB antes do parse. Escritas têm
bucket Redis separado, teto `JOB_RATE_LIMIT_PER_USER` (default 30/h), fail-closed.

Salvar comprova somente armazenamento, não validade/cota/acesso externo. Disponível
significa provider suportado nesta aplicação; não garante rede/modelo carregado.
Falhas de credencial/provider são explícitas, sem troca silenciosa de engine/origem.

## Seleção e proveniência

Quando provider/detecção são omitidos no POST jobs, o servidor usa preferências.
Override explícito por job continua válido. Antes de upload/queue:

- Automático transcrição: AssemblyAI próprio se houver credencial; senão Whisper.
  Não tenta Whisper depois de erro AssemblyAI. Uma credencial existente mas
  indisponível para decriptação não autoriza fallback.
- Automático Intelligence: Gemini (único suportado atualmente), credencial própria
  primeiro. Conta pública sem chave não gera análise com chave USAGI.
- Identidades locais provisionadas pelo operador mantêm compatibilidade platform
  explícita quando não há chave própria e a política daquele provider permite.
  AssemblyAI platform ainda exige reserva/teto; não constitui benefício de signup.
- Origem `user` não toca ledger/orçamento platform, mas preserva limites de upload,
  duração, timeout, rate limiting e ownership. A cota/cobrança é da conta do usuário.

Job/revisão guardam provider, credential_source, credential_id e usuário da
credencial, nunca secret. Redis recebe só ID do job. Worker decripta envelope
vinculado ao usuário/provider e instancia client próprio dentro do work horse;
não reutiliza client platform para BYOK. Gemini SDK legado permanece, sem novo
provider ou migração SDK. Processos filhos supervisionados isolam os clients por job.
Grounding, schema/revisões e revisão humana P3 não mudam.

Substituição cria novo ID e elimina ciphertext anterior; jobs pendentes não adotam
a substituta: FK SET NULL com origem `user` preservada produz falha segura. Remover
é idempotente e não renova orçamento. Uma chamada que já leu a chave/em andamento
pode terminar; remoção local não revoga a chave na conta do provider nem cancela
remotamente essa chamada. Revoke também no provider se necessário.
AssemblyAI BYOK grava provider_attempted_at antes da chamada; recovery não reenvia
tentativa ambígua automaticamente, mesmo usando cota própria. Operador/usuário deve
decidir nova execução; não apagar marker para retry cego.

## Proteção e implantação

`cryptography==50.0.2` (já presente no Worker estável, agora dependência explícita
também da API) fornece Fernet autenticado. Sem criptografia caseira. Envelope
contém user_id/provider/secret; troca de ciphertext entre contas/providers falha.
Ciphertext no PostgreSQL, chave separada em `PROVIDER_CREDENTIAL_ENCRYPTION_KEY`,
somente API/Worker. Nunca reutilizar SECRET_KEY. Sem chave válida, API pode iniciar,
mas escrita/execução BYOK falha com 503/erro seguro; não há armazenamento plaintext.

A chave deve ser Fernet (32 bytes aleatórios codificados base64 URL-safe), gerada
com `Fernet.generate_key()` num processo privado. Configure localmente sem enviar
ao chat, logs, Git, Trello ou frontend. Não há chave gerada automaticamente nem
alteração do .env do operador nesta Task. Recrie API/Worker depois de configurar.
Não usar overrides/chaves sintéticas de testes fora do ambiente isolado.

Guardar backups do banco e chave em locais protegidos separados. Perda/troca da
chave impede decriptação; não rotacionar sobrescrevendo env sem recriptografar e
validar restore. Rotação automatizada/KMS não implementados: procedimento exige
backup, janela sem writes e recriptografia verificada antes de retirar a chave
antiga. Isto deve ser tratado antes de operação pública com credenciais reais.
TLS, acesso mínimo ao banco/env e redaction no proxy continuam necessários.
Não ativar body/header debug logging em rotas de credentials. Interface guarda
input só em memória durante edição e limpa após salvar/falhar; nunca retorna keys.

Alembic 0009 é aditiva, após 0008. Preferências e chaves fazem cascade ao excluir
usuário. Downgrade recusa dados BYOK/preferências/proveniência existentes. Aplicar
no banco real somente após backup/restore e conferência do destino; validação
isolada não autoriza migração de volumes desconhecidos ou banco de terceiros.

## Limites da validação

Esta entrega valida API/Worker/HTTP/Redis/RQ com contas/chaves sintéticas e providers
simulados, sem novas chamadas pagas. AssemblyAI/Gemini reais foram homologados
funcionalmente em fases anteriores; isso não prova validade de uma chave BYOK nova.
Produção, walkthrough visual, novas métricas ML e Pyannote 4 não homologados.
Retenção/consentimento/eliminação remotos continuam gates de implantação descritos
em [AssemblyAI](assemblyai.md). Não há OpenAI/Anthropic, billing ou novas IAs.

Referência: [Fernet — documentação oficial](https://cryptography.io/en/latest/fernet/).
