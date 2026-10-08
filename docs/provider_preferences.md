# Preferências e credenciais próprias de providers

## Contrato por conta

Novas gravações BYOK e inferências exigem Starter/Business ou beta explícito válido.
Todas as contas existentes começam Free, inclusive locais/administradores; o papel
não concede processamento. Chaves existentes não são apagadas: metadata e remoção
continuam disponíveis. Veja [planos e reservas](account_plans.md).

Configurações → Serviços de IA / Transcrição salva preferências no PostgreSQL, não no JWT nem em
localStorage. Transcrição: `automatic`, `whisper`, `assemblyai`. Resumo inteligente:
`automatic`, `gemini`. Detecção de falantes tem default por conta e override por job.
Guest não acessa este contrato: usa apenas um exemplo sintético read-only, sem
inferência, credencial ou BYOK. Resultados Guest anteriores preservam seus contratos.
Minha conta consulta os dados persistidos em `/auth/me`;
não oferece edição sem suporte de persistência no backend.

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

`platform_access` informa separadamente se o fornecimento USAGI está autorizado
e configurado para a conta. Para AssemblyAI inclui uma consulta somente leitura
à margem disponível para a reserva conservadora existente; a reserva transacional
na criação do trabalho continua sendo a decisão final. Não retorna orçamento,
chave ou preços. A chave própria e sua possibilidade de cadastro não dependem
desse acesso: integração suportada, fornecimento USAGI, elegibilidade da opção
e armazenamento BYOK são estados distintos. Nenhum deles comprova conectividade
ou validade de chave no serviço externo.

## Seleção e proveniência

Quando provider/detecção são omitidos no POST jobs, o servidor usa preferências.
Override explícito por job continua válido. Antes de upload/queue:

- Automático transcrição: AssemblyAI próprio se houver credencial; senão Whisper.
  Não tenta Whisper depois de erro AssemblyAI. Uma credencial existente mas
  indisponível para decriptação não autoriza fallback.
- Automático Intelligence: Gemini (único suportado atualmente), credencial própria
  primeiro; a credencial da plataforma exige capability beta explícita.
- Origem de cadastro/papel de admin não concedem uso platform. AssemblyAI exige
  capability, reserva/teto global e franquia USAGI configurada.
- Origem `user` não toca franquia/orçamento platform; o ledger registra uso BYOK
  separadamente, preservando duração, armazenamento, fila, concorrência e rate limits.
  A cota/cobrança externa é da conta do usuário.

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

## Experiência de configuração

A tela separa **como processar** (preferência) de **quem fornece/paga** (origem
resolvida pelo servidor). O painel de serviço selecionado usa preferências salvas;
editar os selects não muda o estado ativo antes de salvar. Atualizar recarrega
capabilities da conta, além do diagnóstico. Opções explícitas são oferecidas
somente quando `available`, `allowed` e `configured` permitem: `available` sozinho
significa suporte, não autorização nem disponibilidade de rede. Uma preferência
salva que ficou indisponível permanece visível/desabilitada, com orientação para
conectar a chave ou escolher outra opção; não é substituída silenciosamente.

| Opção | Processamento / consumo |
|---|---|
| Local (quando permitido) | Faster-Whisper, sem conta externa; não é Guest |
| AssemblyAI próprio | Consumo cobrado diretamente na conta AssemblyAI do usuário |
| Fornecido pela USAGI (quando permitido) | Usa a franquia/créditos da plataforma, conforme política já existente |
| Gemini próprio | Resumos inteligentes consumidos na conta Gemini do usuário |
| Automático | AssemblyAI próprio salvo ou local; para resumos, Gemini; sem retry em outro serviço após erro |

Conectar/substituir envia a chave somente no corpo POST autenticado. O campo
password é temporário em memória e limpo ao enviar/falhar/cancelar/sair da tela;
nenhuma chave vai para stores persistentes, URL, analytics ou mensagens. Após
salvar, **Credencial salva** significa chave armazenada, com ajuda explícita de que não
foi testada no serviço. Só metadata segura (`configured`, `updated_at`) é exibida.
Remover exige confirmação com aviso sobre trabalhos aguardando a chave e sobre
a ausência de revogação remota. Armazenamento BYOK indisponível é comunicado mesmo
quando o processamento fornecido pela USAGI ainda está permitido.
O formulário abre por **Conectar minha API** ou **Substituir chave**. Remoção
continua disponível mesmo sem a chave de criptografia no ambiente: elimina
o registro do próprio usuário sem decriptar ou contornar a proteção.

Limites deliberados da UX: não existe preflight/teste externo de chave, consulta
de saldo ou cota, nem seletor independente para usar a chave plataforma enquanto
há chave própria salva. Formato inválido recebe feedback seguro; rejeição real,
quota e falha do serviço só podem ser conhecidas durante a execução e seguem os
erros seguros já existentes. Não há OpenAI/Anthropic ou nova API nesta entrega.

Validação local P5-02: regressões de Automatic/indisponibilidade/origem, rascunho,
troca/remoção confirmada e erro seguro; suíte backend completa com PostgreSQL/RQ
em banco descartável e Alembic check; navegador Chromium com API PostgreSQL
isolada confirmou salvar, refresh, logout/login, duas contas, adicionar/substituir/
remover chaves sintéticas, resposta inválida controlada e ausência de segredo no
DOM/storage/metadata. Screenshots desktop (1480 px) e mobile (390 px) inspecionadas,
sem overflow ou page errors. Um erro HTTP 422 deliberadamente simulado aparece
no console; nenhum erro inesperado. Nenhuma chamada paga ou nova homologação de
providers/produção; o navegador integrado estava indisponível e foi usado o
Playwright local já aceito. Pyannote 4 permanece não promovido.
