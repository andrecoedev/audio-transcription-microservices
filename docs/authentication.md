# Identidade e autenticação

Auditoria do código integrado e do ambiente de desenvolvimento em 2026-10-09:
[diagnóstico, configuração efetiva e plano incremental](authentication_audit.md).
Firebase Google está implementado, mas desligado no ambiente auditado;
Firebase e-mail/senha continua pendente de implementação.

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

## Configuração Firebase e homologação

A integração permanece desligada por padrão. Para preparar uma homologação,
configure no projeto Firebase o provider Google em Authentication → Sign-in
method e inclua o domínio real da aplicação em Authentication → Settings →
Authorized domains. O domínio precisa corresponder ao host usado pelo navegador;
localhost é apenas para desenvolvimento.

Use os arquivos de exemplo `modules/backend/.env.example` (ou o modelo dev/prod)
como referência. Substitua o valor candidato `your-firebase-project-id` pelo
Project ID real tanto em `FIREBASE_PROJECT_ID` quanto em
`VITE_FIREBASE_PROJECT_ID`; configure também os quatro campos Web
`VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`,
`VITE_FIREBASE_PROJECT_ID` e `VITE_FIREBASE_APP_ID`. Esses valores Web são
incluídos no bundle público do frontend. Não coloque service-account JSON,
chave privada, Admin SDK ou outro segredo nos campos `VITE_*` ou em argumentos
de build.

Para homologação local com ADC, obtenha uma credencial de service account do
projeto de teste por um canal seguro e salve-a localmente em
`.local-artifacts/firebase-adminsdk.json` (diretório ignorado pelo Git). Não
registre o arquivo nem seu conteúdo. Inicie com o overlay, mantendo a montagem
somente leitura e restrita ao container API:

```powershell
docker compose -p usagidev --env-file modules/backend/.env `
  -f compose.yaml -f modules/backend/docker-compose.firebase.yml `
  up --build -d
```

O overlay ativa Firebase por padrão, aponta ADC para o arquivo montado em
`/run/secrets/firebase-adminsdk.json` e não o passa ao Worker nem ao build do
frontend. A integração depende da permissão ADC necessária para validar tokens;
qualquer permissão deve ser limitada ao projeto/ambiente de homologação. O
frontend deve ser reconstruído depois de alterar valores `VITE_FIREBASE_*`, pois
eles são estáticos no bundle.

Homologação real continua pendente até validar o provider Google, os domínios
autorizados, ADC e o fluxo completo no projeto configurado. Não há senha Firebase:
quando `FIREBASE_AUTH_ENABLED=true`, novos cadastros públicos usam Google; senhas
locais existentes e seus `users.id`, vínculos e ownership são preservados. Não
apague ou recrie contas para alternar o provider.

## Sessão, endpoints e rollback

A persistência Google usa `browserLocalPersistence` e `authStateReady` do SDK
oficial. Cada request obtém um ID Token pelo SDK; se o servidor retornar 401,
o frontend força uma renovação e repete a solicitação no máximo uma vez,
somente para a mesma conta interna e Firebase UID. Provas Guest e headers
explícitos não são substituídos. Uma segunda rejeição encerra a sessão;
revogação e usuário desabilitado continuam verificados pelo Admin SDK.
Não há token eterno nem cópia manual de credenciais Firebase no storage da UI.

Uma falha transitória de rede/verificação não apaga a sessão SDK. No startup,
a aplicação mostra uma ação para tentar novamente e não renderiza os recursos
privados até verificar a identidade interna. Logout explícito não pode ser
desfeito por uma restauração em andamento. Mudanças de conta/logout em outras
abas são observadas pelo SDK, com nova verificação da identidade quando preciso.
A rota e o contexto Guest da aba são preservados para continuar após autenticar.
O contrato JWT das contas locais existentes não recebeu refresh ilimitado.

Referências: [persistência oficial](https://firebase.google.com/docs/auth/web/auth-state-persistence)
e [getIdToken/renovação oficial](https://firebase.google.com/docs/reference/js/auth.user#getidtoken).
Testes usam SDK/API simulados; não comprovam configuração Google/ADC em produção.

## Conta e senha em Configurações

Minha conta consulta `/auth/me` e apresenta nome/e-mail persistidos como leitura,
não como preferências locais editáveis. O backend não oferece atualização de
perfil, troca ou redefinição de senha legada. Não existe Firebase e-mail/senha
integrado: a validação Firebase admite somente Google. Não se adiciona uma ação
fictícia nem se muda esse contrato para aparentar suporte.

Na sessão Google verificada, a tela aponta para a segurança da conta Google.
Na sessão com senha USAGI, informa que sua alteração ainda não está disponível.
O vínculo seguro com Google existente continua disponível quando configurado,
com reautenticação pela senha atual; não equivale a troca de senha. A tela rejeita
uma resposta de conta com ID diferente do usuário interno atual e oculta dados
anteriores durante a troca de identidade.

`POST /auth/firebase` recebe somente o ID Token no header Bearer, verifica a
identidade e resolve/cria o usuário interno. Não emite outro JWT para contornar
revogação. Requests privados Firebase usam ID Token atualizado pelo SDK e são
verificados no servidor; privilégios vêm do usuário interno, não de custom claims.
`POST /auth/firebase/link` exige sessão local, senha local novamente e ID Token
Google recente no body. O frontend apaga a senha do campo antes do request e não
armazena esses dados. Nunca enviar tokens em URL.

O SDK Web mantém a sessão Google e faz refresh; Zustand guarda apenas metadados
do usuário e o tipo de sessão, sem copiar ID/refresh tokens. Sair encerra a sessão
SDK deste navegador e limpa acesso local; não é revogação global em todos os
dispositivos. O servidor verifica revogação e usuário Firebase desabilitado.
Falhas de verificação/ADC/Redis não concedem acesso. Tokens do Auth Emulator não
são aceitos pela aplicação; testes usam mocks sem credenciais reais.

Login existente continua em `/auth/login`. Com Firebase habilitado, `/auth/signup`
retorna conflito e orienta usar Google, evitando um segundo cadastro com senha.
`/auth/config` publica apenas flags e Project ID. Guest continua independente e
o resultado temporário é reivindicado somente mediante ação explícita.

A migration `20261003_0010` não modifica ownership nem apaga usuários. Desabilitar
Firebase preserva dados, mas usuários sem senha precisarão da integração para
entrar novamente. Downgrade exige ausência de vínculos e usuários sem senha:
não remova identidades para forçar rollback. Faça backup e planeje a reversão
antes de uma implantação real.

Para preparar Google Sign-In e distinguir configuração manual de validação
automatizada, consulte [ativação e homologação Firebase Google](firebase_google_setup.md).

O SDK Firebase Web traz dependências de produtos não usados pelo app. A override
de `@grpc/grpc-js` para `1.13.6` corrige advisories transitivos da cadeia Node
Firestore; o frontend importa somente `firebase/app` e `firebase/auth`. Não há
Firestore nem Storage na arquitetura do produto. A versão foi validada por
testes de Auth/build, e `npm audit --omit=dev` ficou sem achados nesta Task.
