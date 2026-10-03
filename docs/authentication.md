# Identidade e autenticação

## Auditoria antes de Firebase (P5-03)

`services/identity.py` cria usuários persistentes PostgreSQL (`users.id`), valida
bcrypt e provisiona somente o administrador configurado explicitamente. Cadastro
público não recebe admin nem associa ownership legado. `/auth/login` e `/signup`
emitem JWT HMAC com issuer/audience/exp/iat/sub/jti. As dependências de segurança
reconsultam usuário ativo e papéis no banco; JWT não substitui autorização.

Transcrições usam `TranscriptionOwnership.user_id`; Meetings, tarefas e revisões
derivam autorização da transcrição. Preferências, credenciais BYOK e proveniência
referenciam `users.id`. UID/e-mail externos não podem substituir essas FKs.
`owner_sub` permanece ponte legada por correspondência exata, nunca aproximação.

Guest não é uma conta: proof JWT de propósito separado e `guest_sessions` com TTL,
ownership temporário, limites e claim explícito mediante prova + autenticação.
Frontend guarda essa prova em sessionStorage da aba. Não transferir apenas porque
alguém fez login; não colocar prova em URL nem Firebase.

Antes desta Task, Zustand persistia usuário/JWT em `auth-storage`, com cópia do JWT
em `localStorage.token`; App restaurava com `/auth/me`, logout apagava a sessão
local. Login/signup navegavam sempre para `/`; `saveGuest=1` apenas sobrevivia entre
links e não devolvia o contexto. Isso pode deixar o visitante longe do trabalho.

## Decisão de integração

Firebase é camada de identidade, não banco/domínio. Google usa SDK Web oficial;
FastAPI verifica ID Token via Admin SDK (assinatura, issuer/audience/projeto,
expiração, revogação e usuário Firebase desabilitado), exige Google e e-mail
verificado. Mapping único `(project_id, uid)` aponta para `users.id`. Não confiar
em UID/e-mail fornecidos livremente, nem em custom claims para dar admin/scopes.

Usuário novo é público, não-admin, sem senha local; nenhuma credencial paga da
plataforma é concedida. Identidades locais existentes permanecem intactas. Colisão
de e-mail não vincula/mergeia automaticamente: exige login na conta USAGI existente,
nova confirmação de sua senha local e token Google verificado com autenticação
recente. Prova de ambas as contas pode vincular e preservar o mesmo `users.id`;
vínculo já pertencente a outra conta é rejeitado. Não transferir recursos entre
usuários ou atribuir ownership por e-mail.

Nesta Task não há senha Firebase: bcrypt continua o único sistema de senha, para
contas existentes. Ao habilitar Firebase, o cadastro público novo passa a Google;
com integração desabilitada, o contrato anterior continua disponível. Desativar a
integração não apaga usuários/vínculos. Downgrade deve recusar perda de vínculos
ou usuários sem senha; não inventar senha para uma identidade federada.

Riscos tratados: colisão de UID entre projetos, concorrência de primeiro login,
takeover por e-mail, confusão entre JWT local/Guest/Firebase, sessão persistida
obsoleta, revogação e credencial administrativa no bundle. Guest permanece
experimentável; claim continua explícito ao retornar ao trabalho.

Fontes oficiais: [verificar ID Tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens),
[sessões e revogação](https://firebase.google.com/docs/auth/admin/manage-sessions),
[Google no SDK Web](https://firebase.google.com/docs/auth/web/google-signin),
[persistência Web](https://firebase.google.com/docs/auth/web/auth-state-persistence).
