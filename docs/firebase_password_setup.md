# Firebase e-mail/senha e transição de contas

## Autoridades e escopo

Firebase autentica Google e, quando explicitamente habilitado, e-mail/senha.
PostgreSQL mantém `users.id`, perfil, planos, concessões, ownership, reuniões,
BYOK e consumo. Os métodos Firebase pertencem ao mesmo UID; não criam um usuário
interno por método. O mapping existente `(project_id, uid)` continua suficiente:
esta etapa não acrescenta migrations nem modifica contas em massa.

O login local permanece como caminho explícito para contas antigas. Não há
fallback automático para senha local quando Firebase falha. Hashes bcrypt não
são copiados para Firebase, removidos ou usados como senha nova.

## Preparação manual e ativação

1. Siga [a configuração Google/ADC](firebase_google_setup.md). Google deve
   continuar funcional antes de acrescentar o método password.
2. No projeto correto do Firebase Console, habilite Authentication > Sign-in
   method > Email/Password. Login por link não faz parte desta implementação.
3. Configure política de senha e proteção contra enumeração de e-mails no Console.
   A UI pede no mínimo 12 caracteres e consulta a política oficial pelo SDK;
   o serviço pode exigir outros critérios. A configuração do Console deve
   impor a política desejada também a chamadas diretas.
4. Revise templates/idioma de verificação e redefinição e domínios autorizados.
   Os links usam os handlers oficiais hospedados pelo Firebase, incluindo
   tratamento de código expirado/inválido. Não copie links com códigos para logs.
5. Defina `FIREBASE_PASSWORD_ENABLED=true` no arquivo local ignorado da API.
   O default é `false`; a flag não ativa o método no Console. A API só anuncia
   `firebase_password_enabled` se ambas as flags Firebase estiverem ativas.
6. Rebuild API/frontend e preserve o overlay ADC. Para GPU no Windows:

```powershell
docker compose -p usagidev --env-file modules/backend/.env --env-file .env.firebase.local -f compose.gpu.yaml -f modules/backend/docker-compose.firebase.yml up --build -d api frontend
```

O Worker não recebe ADC, configuração administrativa ou senhas Firebase.
Nenhuma credencial nova ou alteração IAM é necessária nesta etapa. Uma falha
ADC/projeto/permissões deve ser corrigida operacionalmente, não contornada
desabilitando validação/revogação.

## Cadastro, verificação e sessão

O SDK oficial cria a conta Firebase e envia verificação. A senha não passa por
um endpoint de senha USAGI e não é persistida no frontend ou PostgreSQL.
Uma conta não verificada permanece em estado pendente: não recebe sessão do
domínio, não cria usuário interno e não acessa recursos privados. O backend
exige `email_verified` no token validado, tanto no login quanto em requests
autenticados. Nenhuma flag enviada livremente pelo cliente é aceita como prova.

Após confirmar o link, a UI recarrega o usuário SDK e força renovação do ID Token.
Só então `/auth/firebase` resolve/cria o usuário interno Free, sem grants ou
privilégios administrativos. Contexto de retorno e Guest são preservados.
SDK `browserLocalPersistence`, `onIdTokenChanged` e os interceptors existentes
continuam responsáveis pela sessão renovável. Estado SDK pendente não equivale
a uma sessão privada USAGI. Logout explícito e revogação continuam respeitados.

Reenvio tem cooldown UI e é sujeito às proteções/quotas do Firebase; o cooldown
não é um controle de autorização nem substitui limites do serviço. Reset exibe
feedback neutro, inclusive quando o SDK retorna conta não encontrada. A proteção
de enumeração deve também ser configurada no Firebase. Endpoints do domínio
mantêm o rate limiting Redis existente, inclusive login/link e falha segura.

## Migração iniciada pelo usuário

1. Entre explicitamente com usuário/senha da conta USAGI existente.
2. Em Minha conta, escolha conectar um acesso por e-mail existente ou criar um
   acesso Firebase. Não use primeiro login de conta nova para migrar dados.
3. Autentique a identidade de destino; se necessário, confirme seu e-mail.
4. Confirme novamente a senha local. `/auth/firebase/link` exige sessão local,
   senha válida e token Firebase verificado com `auth_time` de até cinco minutos.
   Se a confirmação demorar, autentique novamente o destino antes de vincular.
5. O vínculo é transacional, idempotente e protegido por constraints e lock do
   usuário. UID pertencente a outra conta ou usuário já vinculado a outro UID
   retorna conflito: não há merge nem substituição automática de identidade.

O endpoint tem nome histórico e agora admite os dois métodos validados.
Mesmo e-mail não autoriza associação; as duas provas são obrigatórias. Dados,
hash local, `users.id`, planos, grants, reservas e ciphertext BYOK não mudam.
Adicionar Google/senha a uma conta Firebase usa `linkWithPopup`/
`linkWithCredential` oficiais no UID atual, não outro `signInWithPopup`.

## Rollback e limites

Desabilitar password na API impede entrada password; não remove vínculos/dados
nem afeta login Google/local. Usuários exclusivamente password precisam desse
método operacional para entrar: rollback não é licença para bloquear essas
contas indefinidamente nem lhes atribuir senha local. Remover o login legado
exige decisão posterior e inventário/homologação próprios.

Não há recuperação automática de ownership legado por reset Firebase. Sem prova
da senha local, um conflito exige procedimento de suporte separado. Contas
Firebase distintas não são mescladas por e-mail, nem UIDs substituídos.

## Estado observado e homologação

Base desta etapa: `origin/dev` com PR #22 integrado, `1bb366d`. O usuário informou
Google homologado localmente para conta nova/vínculo. Na auditoria somente leitura
do banco de desenvolvimento `transcription_db`, havia duas contas, uma com senha
local e uma binding Firebase, sem órfãos. Não houve migração de contas reais.

A consulta real Admin de configuração respondeu 200 e indicou Email/Password
desabilitado. Portanto testes SDK simulados e PostgreSQL descartável não comprovam
homologação real de password. Antes de liberar, verificar com contas sintéticas
autorizadas: signup, recebimento/verificação, reenvio, login, reset e link expirado,
refresh/reabertura/logout, Google, migração preservando ID/ownership/plano/BYOK,
conflito e isolamento. Não registrar e-mails pessoais, senhas ou tokens como
evidência. Homologação local não equivale a produção homologada.

Referências: [Password Web](https://firebase.google.com/docs/auth/web/password-auth),
[gerenciamento de usuários](https://firebase.google.com/docs/auth/web/manage-users),
[account linking](https://firebase.google.com/docs/auth/web/account-linking).
