# Auditoria de autenticação — 2026-10-09

> Este documento preserva a auditoria anterior ao PR #22. O PR foi integrado e
> o usuário informou Google homologado localmente. A próxima etapa de senha,
> coexistência e migração está descrita em
> [firebase_password_setup.md](firebase_password_setup.md), distinguindo
> implementação/testes simulados de homologação real pendente.

## Diagnóstico

A P5-03 implementou **Google via Firebase opcional**, com validação no servidor e
associação ao usuário interno. Não implementou Firebase e-mail/senha. No ambiente
de desenvolvimento inspecionado, Firebase está desabilitado e a configuração Web
não foi incorporada ao frontend. Portanto, o login observado é o fluxo local
USAGI: usuário/senha, bcrypt no PostgreSQL e JWT emitido pelo backend.

A arquitetura desejada (Google e e-mail/senha no Firebase; domínio no PostgreSQL)
é compatível com a associação existente, mas exige completar o método de senha,
a interface e a configuração. Apenas habilitar uma variável não resolve isso.

Esta auditoria não alterou código de autenticação, configuração, credenciais,
usuários, permissões ou migrations. Não criou a conta beta solicitada antes da
auditoria. Não realizou login Firebase real nem autenticou contas do usuário.

## Escopo e evidência verificável

- `origin/dev` foi atualizado por fetch: `3b8fff936284d8185c1d3ed0769bbf1fc036ee26`
  (merge do PR #21). Checkout auditado: `e5d2c91a4eab28ab7805b791ee3560476d42e51a`,
  branch `feat/groq-meeting-intelligence`. Os arquivos centrais de autenticação
  comparados não diferem de `origin/dev`.
- Stack em execução: `usagidev-api-1`, `usagidev-frontend-1`,
  `usagidev-postgres-1`, Redis e Worker; containers saudáveis na inspeção.
- `GET http://localhost:2020/auth/config` e o mesmo endpoint pelo proxy
  `http://localhost:3000/api/auth/config` responderam:
  `firebase_enabled=false`, `firebase_project_id=null`,
  `local_signup_enabled=true`, autenticação estrita.
- A API confirmou `APP_ENV=dev`, driver `postgresql+psycopg`, host `postgres`,
  banco `transcription_db`. Só depois dessa identificação foi aberta uma
  transação com `SET TRANSACTION READ ONLY` para as contagens abaixo.

| Medida no banco de desenvolvimento | Resultado |
| --- | ---: |
| Revisão Alembic | `20261009_0014` |
| Usuários totais / ativos | 2 / 2 |
| Usuários com senha local / sem senha local | 2 / 0 |
| Vínculos em `firebase_identities` | 0 |
| Vínculos Firebase órfãos | 0 |
| Ownership com `owner_sub` e sem `user_id` | 0 |

Nenhum e-mail, username, hash, token, transcrição ou credencial dessas contas foi
incluído nas saídas. As contagens não constituem inventário de produção.

## Métodos e contratos atuais

| Experiência | Implementação real | Endpoint USAGI | Estado |
| --- | --- | --- | --- |
| Entrar com usuário/senha | Bcrypt local, `User.hashed_password`; JWT USAGI | `POST /auth/login` | Ativo; o identificador é username, não e-mail |
| Cadastro com username/e-mail/senha | Cria `User` público Free, sem privilégios | `POST /auth/signup` | Ativo quando Firebase está desligado; responde 409 quando ligado |
| Continuar com Google | SDK Web, `GoogleAuthProvider`, `signInWithPopup`, ID Token | `POST /auth/firebase` | Implementado; oculto no ambiente auditado |
| Vincular Google a conta legada | Sessão local + senha atual + token Google recente | `POST /auth/firebase/link` | Implementado; UI depende da configuração Google |
| Firebase e-mail/senha | Sem chamadas Web correspondentes; token com método `password` rejeitado | Não existe fluxo de cadastro/login específico | Não implementado |
| Consulta de sessão | Revalida identidade e usuário ativo interno | `GET /auth/me` | Usado por ambos os tipos de sessão |
| Logout | Limpa estado local; sessão Firebase usa `signOut` | Sem endpoint de revogação global | Implementado no navegador |

Fontes: `modules/frontendv2/src/pages/Login.jsx`,
`services/authService.js`, `services/firebaseAuth.js`,
`components/GoogleAccountLink.jsx`; backend `src/routers/auth.py`,
`src/services/identity.py` e `src/security.py`.

Não foram encontradas implementações de `signInWithEmailAndPassword`,
`createUserWithEmailAndPassword`, `sendPasswordResetEmail`,
`sendEmailVerification` ou `linkWithCredential` no código de produto.
Configurações informa corretamente que a senha local não possui alteração ou
redefinição disponível nesta versão.

## Por que o botão Google não aparece

`Login.jsx` mostra o botão somente se todas estas condições forem satisfeitas:

1. `/auth/config` retorna `firebase_enabled=true` e Project ID válido;
2. o bundle contém API key Web, auth domain, Project ID e App ID;
3. o Project ID Web coincide com o Project ID informado pela API.

`GoogleAccountLink.jsx` usa a mesma condição. Falha de consulta, configuração
incompleta ou divergência de projeto oculta o botão. Nesta execução, a condição
da API já é falsa; também foi confirmada configuração Web ausente no bundle
principal servido. O texto do botão existe nesse bundle, portanto o recurso não
foi removido da implementação.

| Configuração / dependência | Evidência local | Consequência |
| --- | --- | --- |
| `FIREBASE_API_KEY` | Presente no `.env` backend; valor não exibido | Esse nome não é consumido pelo adaptador Web nem convertido pelo Compose |
| `FIREBASE_AUTH_ENABLED` | Ausente nesse arquivo; API efetiva `false` | Firebase desligado pelo default |
| `FIREBASE_PROJECT_ID` | Ausente no arquivo e na configuração efetiva | API não tem projeto Firebase selecionado |
| `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID` | Ausentes no arquivo local; nenhuma configurada na inspeção do bundle servido | `firebaseAuth.isConfigured()` não tem configuração completa |
| `GOOGLE_APPLICATION_CREDENTIALS` | Não definido no container API; nenhum arquivo configurado por essa variável | Overlay de credencial administrativa não está ativo; ADC efetiva não foi homologada |
| `FIREBASE_AUTH_EMULATOR_HOST` | Ausente na API | Sem configuração de emulator herdada |
| SDK Admin | `firebase-admin==7.7.0` instalado na API e declarado em `requirements.api.txt` | Dependência presente; instalação não comprova ativação |
| SDK Web | `firebase==12.19.0` declarado em `package.json`; integração incluída no build servido | Código disponível, condicionado à configuração |

`compose.yaml` inclui `modules/backend/docker-compose.yml`. O serviço frontend
usa `Dockerfile.web`, que recebe as quatro variáveis públicas como argumentos
Vite durante o build. Mudar o `.env` depois do build não atualiza o bundle.
O `Dockerfile` alternativo do frontend não é o arquivo usado por esse Compose.

O overlay existente `modules/backend/docker-compose.firebase.yml` habilita
Firebase por default (uma variável explícita `false` ainda prevalece) e monta
ADC somente leitura na API. Não envia a credencial administrativa ao Worker ou
frontend. A API key Web é configuração pública do Firebase e não substitui ADC,
o Project ID, a habilitação do método no console ou os domínios autorizados.

Google habilitado no Firebase Console, domínios autorizados, configuração de
contas/provedores do projeto e permissões ADC não foram verificados remotamente.
Sua ausência não foi presumida. Essas verificações continuam necessárias para
homologar o projeto real.

## Validação no servidor e associação ao domínio

`firebase_identity._verify_with_sdk` usa Admin SDK oficial e
`verify_id_token(..., check_revoked=True, clock_skew_seconds=0)`.
`verify_firebase_token` exige projeto configurado e habilitado, restringe tamanho
do token, recusa emulator e verifica audience, issuer, UID/sub, e-mail válido e
verificado, ausência de tenant e `auth_time`. Hoje exige
`firebase.sign_in_provider == 'google.com'`; `password` recebe 401.
Falhas de token retornam 401; indisponibilidade do serviço retorna 503 sem
conteúdo sensível.

`firebase_identities` associa a chave composta `(project_id, uid)` a `users.id`.
Há FK e unicidade em `user_id`: uma conta interna pode ter uma identidade
Firebase. O UID pode futuramente possuir vários métodos de entrada no próprio
Firebase. Não é preciso criar um usuário PostgreSQL por método.

`POST /auth/firebase` resolve o vínculo exato. Se não houver vínculo nem colisão
de e-mail, cria usuário público sem senha local e sem privilégios, mais o vínculo,
em transação. E-mail coincidente com conta existente retorna 409, não faz merge.
Concorrência é protegida por constraints e tratamento de `IntegrityError`.
Vínculo existente continua resolvendo o mesmo `users.id`, mesmo que o e-mail do
token mude; não substitui automaticamente o perfil interno.

O link legado exige login local, senha local novamente e autenticação Google com
`auth_time` de até cinco minutos. Provar as duas contas permite associar o UID ao
`users.id` existente; outro vínculo incompatível é rejeitado. Não é uma associação
baseada apenas em e-mail, nem exige que os dois e-mails sejam iguais.

Requests privados tentam validar JWT local; quando necessário e Firebase está
habilitado, verificam o ID Token e consultam o vínculo já existente. Não criam
usuários a cada request. Usuário ativo, papel administrativo, plano, grants e
ownership vêm do banco interno. Custom claims Firebase não concedem admin.

## Sessão e Guest

Firebase usa `browserLocalPersistence`, `authStateReady`, `onIdTokenChanged` e
`getIdToken` do SDK. O interceptor Axios obtém token em cada request, força
renovação após 401 uma vez para a mesma identidade e encerra a sessão após
rejeição definitiva. Headers explícitos e provas Guest não são sobrescritos.
Falha transitória de renovação não é tratada automaticamente como revogação.
`sessionService` verifica `/auth/me` ao restaurar e protege logout/troca de conta
contra respostas antigas. O retorno usa rota interna validada, com contexto
Guest preservado.

Zustand conserva metadata e `authProvider`; ID/refresh tokens Firebase não são
copiados manualmente para esse store. O contrato legado continua armazenando
JWT em `localStorage.token` e no estado persistido, com expiração e sem refresh
local implementado. Essa é uma diferença real de segurança e persistência que a
migração precisa tratar, não uma evidência de que a senha já usa Firebase.

Guest permanece demonstrativo e independente. Prova Guest e reivindicação de
resultados anteriores seguem os contratos existentes: transferência exige prova
e ação explícita; login não deve atribuir dados por e-mail ou contexto visual.

## Riscos e limites confirmados

| Risco / lacuna | Tratamento necessário |
| --- | --- |
| Ativar Firebase agora não cria login Firebase por senha | Implementar SDK Web, validação `password`, verificação de e-mail e recuperação de senha antes de anunciar esse método |
| Cadastro local é bloqueado assim que Firebase é habilitado | Homologar Google e configuração Web antes de ativar; evitar ambiente sem forma utilizável de cadastro |
| Vincular por e-mail causaria takeover ou perda de ownership | Manter prova das duas identidades, associação por UID/projeto e constraints |
| Criar um UID Firebase separado para cada método | Vincular métodos ao mesmo UID pelo fluxo oficial; colisões não podem gerar outro usuário interno |
| UI identifica qualquer sessão/vínculo Firebase como Google | Antes de aceitar `password`, revisar `google_connected`, `_firebase_response`, `AccountSettings` e metadata segura do método de entrada |
| JWT legado persiste em storage acessível a JavaScript | Coexistência temporária; preservar acesso enquanto se migra, definir posteriormente retirada do fluxo legado |
| Desligar Firebase bloqueia novos logins de usuários sem senha local | Rollback precisa preservar integração utilizável para essas contas; não inventar senha nem remover bindings |
| Console/ADC/projeto real não homologados | Validar com contas de teste autorizadas; testes simulados não comprovam autenticação real |
| Migração destrutiva de `users` | Não trocar IDs, recriar contas, remover FKs ou reatribuir recursos |

Não foram encontradas nesta auditoria provas de autenticação Firebase real ativa.
A consulta local encontrou zero bindings. Isso não permite concluir nada sobre
outra implantação ou sobre usuários no Firebase Console.

## Plano incremental recomendado — ainda não implementado

### 1. Preparação e inventário

Identificar cada destino/ambiente, auditar contas e vínculos por contagens e
conflitos, preservar backup e validar restore antes de mudanças de banco.
Inspecionar normalização de e-mail, vínculos órfãos e ownership legado sem
descartar registros. Definir projeto Firebase canônico e um UID por usuário.
Manter plano, privilégios, grants, preferências e BYOK atuais.

### 2. Homologar Google existente

Configurar os quatro valores Web públicos, Project ID backend, credencial ADC
restrita e Google/domínios autorizados no Firebase Console. Rebuild do frontend e
recriação controlada da API; conferir `/auth/config` e o bundle com saídas seguras.
Testar Google com conta de teste nova e link de uma conta legada existente,
preservando `users.id`. Não habilitar o cadastro Google antes dessa prova.

### 3. Completar Firebase e-mail/senha

Habilitar o método no Firebase Console e implementar os fluxos oficiais de
cadastro, login, envio de verificação, redefinição e reautenticação. A senha nova
vai ao SDK Firebase, não a `/auth/login` nem ao PostgreSQL.
Exigir e-mail verificado para admissão ao domínio; a interface deve explicar o
estado pendente de verificação. Enviar o ID Token ao mesmo ponto de entrada
USAGI, e estender a allow-list para `google.com` e `password` preservando todos os
demais controles. Diferenciar método de login da identidade interna na metadata
segura e em Configurações. Não rotular toda sessão Firebase como Google.

### 4. Migrar contas legadas por ação autenticada

Reutilizar/generalizar o fluxo de vínculo explícito: sessão local válida, senha
legada novamente e token Firebase recente/verificado. Associar o UID ao mesmo
`users.id`, em transação auditada, sem duplicar ou mover recursos. Uma identidade
Firebase já vinculada a outra conta é conflito, não gatilho para merge.

Google e senha Firebase devem ser vinculados ao mesmo UID usando o mecanismo
oficial de account linking. Usuários com e-mail coincidente continuam recebendo
orientação para entrar na conta existente e prová-la. Contas sem acesso à senha
legada precisam de recuperação verificada definida separadamente; não basta
enviar reset Firebase e inferir ownership pelo e-mail.

Recomenda-se essa migração gradual iniciada pelo usuário, sem importação em lote
de hashes nesta primeira etapa. É menor e preserva a prova de identidade. O
schema `firebase_identities` é independente do método e provavelmente já atende;
uma nova migration só se houver necessidade concreta identificada no desenho.

### 5. Coexistência, validação e retirada posterior

Manter login legado funcionando durante a migração. Não há autorização nesta
auditoria para apagá-lo ou remover hashes. Retirá-lo exige etapa futura explícita,
inventário de contas ainda não vinculadas, alternativa para administradores e
recuperação de acesso, homologação e decisão de rollout/rollback.

Preservar o mesmo `users.id` mantém `transcription_owners`, reuniões/tarefas e
revisões autorizadas pela transcrição, `user_provider_preferences`, ciphertexts
BYOK, planos/grants, reservas, ledger e audit events. UID/e-mail não devem
substituir essas referências. Não conceder plano ou consumo pago por autenticar.

Antes do rollout: testar os dois métodos, token inválido/expirado/revogado,
primeiro login concorrente, link com/sem provas, colisão de e-mail/UID, mesma
identidade com múltiplos métodos, ownership/BYOK/planos, sessão renovada,
logout/refresh/troca de abas, Guest e retorno ao contexto. Homologar com Firebase
real em desenvolvimento isolado; depois planejar implantação real.

## Evidência de testes existentes e limite desta auditoria

- Backend: `tests/test_firebase_auth.py` cobre claims, rejeição explícita de
  `password`, login/link/corridas lógicas, conflito de e-mail, identidade interna,
  Guest, preferência de outro usuário e bloqueio de signup local. Claims/SDK são
  simulados.
- `tests/test_firebase_sdk.py` verifica opções oficiais e falhas com SDK mockado,
  sem ADC, token real ou conexão Firebase.
- Integrações `test_firebase_identity_runtime.py` e
  `test_firebase_identity_migration.py` usam PostgreSQL isolado e identidade
  sintética; protegem constraints, concorrência e downgrade.
- Frontend: `Login.test.jsx`, `GoogleAccountLink.test.jsx`, `firebaseAuth.test.js`,
  `sessionService.test.js`, `api.test.js`, `authReturn.test.js` cobrem gates de
  configuração, popup/link, refresh, persistência, logout e retorno com mocks.
- Migration `20261003_0010` adiciona bindings e permite senha local nula; downgrade
  recusa vínculos ou contas sem senha. Não muda ownership.

Nesta execução os testes foram inspecionados, não reexecutados. As verificações
executadas foram fetch/diff, HTTP público, dependência/configuração efetiva da
API, leitura segura do bundle e consultas agregadas PostgreSQL somente leitura.
Nenhuma suíte ou autenticação real é declarada aprovada por esta auditoria.

## Fontes oficiais consultadas

- [Firebase Web: e-mail/senha](https://firebase.google.com/docs/auth/web/password-auth)
- [Vincular métodos à mesma conta](https://firebase.google.com/docs/auth/web/account-linking)
- [Validar ID Tokens no servidor](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [Persistência de autenticação Web](https://firebase.google.com/docs/auth/web/auth-state-persistence)

Implementação/operacionalização anterior: [authentication.md](authentication.md).
