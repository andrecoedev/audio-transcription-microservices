# Acesso local de desenvolvimento

Esta concessão permite uso interno antes do Beta sem atribuir Starter, alterar
planos existentes ou habilitar a transcrição gratuita publicamente.

## Fronteira de segurança

A permissão deve ser concedida explicitamente ao usuário interno, é revogável e
auditada. Só funciona com `APP_ENV=dev`, `DEV_LOCAL_ACCESS_ENABLED=true` e
`LOCAL_TRANSCRIPTION_ENABLED=true`. Não depende do papel de administrador nem de
um e-mail presente no request. Fora de desenvolvimento, a concessão não é efetiva.
Ela não declara o ambiente homologado: `LOCAL_TRANSCRIPTION_HOMOLOGATED` mantém
seu significado para o acesso comum.

A exceção é somente para transcrição local. AssemblyAI, Gemini, Groq e BYOK
continuam sujeitos às permissões, configuração, orçamento e limites existentes.
Não existe fallback automático para um serviço pago.

## Comercial versus técnico

Para a execução local autorizada não há franquia mensal nem limite comercial
acumulado de armazenamento. Consumo e reservas continuam persistidos, inclusive
em retries, falhas ambíguas e recuperação. Exclusão não reescreve o histórico.

Não há promessa de recursos físicos infinitos. Permanecem o teto técnico de
upload `MAX_UPLOAD_SIZE_MB` (padrão 5120 MB), validação do arquivo, rate limiting,
fila global, timeout e processamento supervisionado. Os limites técnicos de
desenvolvimento são configuráveis:

| Configuração | Padrão técnico |
|---|---|
| `DEV_LOCAL_MAX_AUDIO_SECONDS` | 86400 segundos |
| `DEV_LOCAL_MAX_QUEUED_JOBS` | 2 aguardando por conta |
| `DEV_LOCAL_MAX_PROCESSING_JOBS` | 1 simultâneo por conta |

Esses valores não são franquias comerciais nem evidência de capacidade
homologada. Arquivos grandes ainda podem exceder memória, disco ou timeout do
hardware disponível; erros devem permanecer explícitos.

## Operação

1. Confirme o banco-alvo e faça backup antes de aplicar a migration aditiva.
2. Aplique Alembic `upgrade head` com a versão desta Task.
3. Configure a habilitação apenas no ambiente de desenvolvimento; API e Worker
   recebem a mesma política através do Compose.
4. Use `PATCH /admin/accounts/{user_id}/development-local-access`, autenticado
   como administrador, com `{"enabled": true, "reason": "operational_access"}`.
   Não conceda acesso a todas as contas nem altere o plano. O identificador é o
   usuário interno; não vincule identidades por aproximação de e-mail.
5. Confira `/account/plan` e `/settings/providers` da conta: o marcador
   `development_access` deve ser verdadeiro. A UI mostra os tetos técnicos.
6. Para revogar, remova a concessão pela mesma operação administrativa; para
   desligar todo o mecanismo, configure `DEV_LOCAL_ACCESS_ENABLED=false` e
   recrie API e Worker. Jobs ainda não iniciados revalidam a permissão.

A coluna de concessão recebe `false` para todas as contas na migration. A mesma
migration amplia `transcription_reservations.stored_bytes` para 64 bits, permitindo
registrar corretamente uploads acima de 2 GB. Downgrade recusa estreitar o campo
enquanto existirem valores que não cabem em 32 bits.

Não use testes que limpam tabelas no banco de desenvolvimento. Os testes de
integração e downgrade/check devem rodar em PostgreSQL exclusivo de testes.
