# Firebase Google Sign-In: ativação e homologação

## Escopo e estado atual

A Etapa 1 mantém login local, Guest, usuários internos, planos, ownership e
credenciais BYOK. Não implementa senha Firebase nem associação automática por
e-mail. A [auditoria](authentication_audit.md) registra o diagnóstico anterior.

Na inspeção local desta etapa, a API respondeu `firebase_enabled=false`, sem
Project ID nem caminho ADC configurados. O SDK Admin estava instalado (7.7.0).
O Worker não recebeu configuração Web nem caminho de credencial administrativa.
O arquivo opcional do overlay não estava disponível. Nenhum login Google real
foi executado: homologação externa permanece **pendente**.

## Alterações de código

- Vite aceita quatro aliases públicos `FIREBASE_*`, além dos nomes canônicos
  `VITE_FIREBASE_*`. Campos canônicos não vazios têm preferência; os demais
  usam o alias correspondente. Arquivos por modo do backend e do frontend são
  lidos com prefixos restritos; o ambiente do processo tem precedência.
- Somente API_KEY, AUTH_DOMAIN, PROJECT_ID e APP_ID são definidos no bundle.
  Chaves de providers, JWT e credenciais administrativas não fazem parte desse
  mapeamento. Nunca prefixe um segredo administrativo com `VITE_`.
- Compose encaminha os mesmos quatro aliases ao build do frontend.
- Configuração incompleta, placeholders ou formatos inválidos não inicializam
  o SDK Web. O botão também exige a flag da API e Project IDs coincidentes.
  Isso valida a configuração local, não a autorização no Firebase Console.
- A verificação oficial Admin e a vinculação segura existentes foram preservadas
  e receberam regressões adicionais. Nenhuma migration ou dependência mudou.

## Configuração manual no Firebase Console

1. Confirme o projeto correto e habilite Google em Authentication > Sign-in
   method, com os dados de suporte exigidos pelo Console.
2. Cadastre os domínios realmente usados em Authentication > Settings >
   Authorized domains, inclusive `localhost` para testes quando necessário.
   Não suponha que domínios locais estejam autorizados automaticamente.
3. Copie a configuração pública do aplicativo Web correto. Verifique restrições
   da API key e configuração OAuth/domínio conforme o ambiente escolhido.
4. Disponibilize à API uma identidade administrativa existente e autorizada
   usando ADC. A verificação com revogação precisa conseguir consultar o estado
   da conta. O projeto não gera service accounts, chaves ou concessões IAM.
   Solicite ao responsável somente as permissões necessárias, sem contornar IAM.

Referências oficiais: [Google Sign-In Web](https://firebase.google.com/docs/auth/web/google-signin),
[Admin SDK](https://firebase.google.com/docs/admin/setup),
[verificação de ID Tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens).

## Configuração local e Compose

Defina nos arquivos locais ignorados os quatro campos públicos com o prefixo
`VITE_FIREBASE_` ou `FIREBASE_`: API_KEY, AUTH_DOMAIN, PROJECT_ID e APP_ID.
Na API, defina `FIREBASE_PROJECT_ID` com o mesmo projeto do aplicativo Web.
Somente após preparar Console e ADC, habilite `FIREBASE_AUTH_ENABLED=true`.
Não versione valores de configuração reais ou conteúdo de credenciais.

O frontend recebe esses valores no **build**; reiniciar um container não altera
um bundle antigo. Refaça o build/recrie API e frontend após configurar.
O Worker não verifica identidade Firebase e não precisa da credencial Admin.

O overlay opcional monta somente na API um arquivo ADC já fornecido pelo
operador, somente leitura. Prefira um diretório privado fora do repositório,
por exemplo `%LOCALAPPDATA%\USAGI\credentials\`, com ACL restrita ao usuário.
Defina `FIREBASE_ADC_HOST_PATH` no arquivo local ignorado `.env.firebase.local`.
Nunca registre um caminho pessoal absoluto no Git. A ausência dessa variável
preserva o caminho legado `.local-artifacts/firebase-adminsdk.json`.
Não crie um arquivo vazio ou aceite
uma montagem de diretório para contornar sua ausência. Após a preparação:

```powershell
docker compose -p usagidev --env-file modules/backend/.env --env-file .env.firebase.local -f compose.yaml -f modules/backend/docker-compose.firebase.yml up -d --no-deps api
```

**Recriações posteriores:** executar apenas o Compose base pode remover o
mount ADC e deixar a flag ativa sem credenciais. Use sempre o comando completo
acima. Para o comando usual `docker compose up` no Windows, é possível configurar
no `.env` local ignorado da raiz `COMPOSE_FILE=compose.yaml;modules/backend/docker-compose.firebase.yml`
e `COMPOSE_PROJECT_NAME=usagidev`, junto do caminho privado, flag e projeto
Firebase públicos. Essa configuração local foi validada nesta execução, sem
alterar o ambiente global. Não sobrescreva um `.env` existente. Ao fornecer
`--env-file` ou `-f` explicitamente, preserve todos os arquivos necessários:
essas opções podem substituir a seleção local padrão.

Durante a tentativa interativa reportada pelo operador, a API foi encontrada
recriada sem overlay e ADC. A montagem foi restaurada e o comando Compose
padrão foi validado com a configuração local acima. Consultas Auth config e
Google provider responderam 200: Google habilitado, cliente OAuth configurado
e `localhost` autorizado. A primeira tentativa Google apresentou erro genérico;
não foi confirmado sucesso após a restauração. Um redirecionamento HTTP 302
observado pelo operador não identifica a falha de autenticação. Não atribuir
definitivamente o erro do popup à ADC sem evidência da requisição correspondente.

Em ambientes com ADC gerenciado, use o mecanismo aprovado daquele ambiente,
sem copiar uma chave para o frontend ou Worker. O overlay local não é uma
prescrição para produção.

Antes de ativar, valide leitura do arquivo pelo Docker, integridade da
transferência, projeto configurado e uma consulta Auth somente leitura com UID
sintético. `UserNotFoundError` nesse teste comprova acesso ao serviço sem criar
usuários. Inicializar o SDK ou renovar OAuth, isoladamente, não comprova acesso
ao Firebase Auth. Após validar, elimine a cópia original no working tree.
Não faça build com credenciais dentro do contexto Docker.

ADC `authorized_user` não contém necessariamente `project_id`: seu projeto de
quota não determina os projetos aos quais o usuário tem acesso. Configure o
projeto explicitamente na API e teste a autorização real. A documentação oficial
alerta sobre restrições de ADC gerado com o cliente OAuth padrão do gcloud;
não generalize uma inicialização bem-sucedida como compatibilidade universal.
Se necessário, o operador deve fornecer um mecanismo já autorizado adequado,
sem o projeto criar credenciais ou alterar IAM.

### Validação operacional posterior à preparação

Nesta execução local, uma ADC `authorized_user` foi transferida para diretório
privado externo, com integridade verificada e ACL restrita. Docker conseguiu
ler o arquivo; OAuth renovou e Firebase Auth respondeu `UserNotFoundError` ao
UID sintético, inclusive dentro da API recriada. `/auth/config` passou a indicar
Firebase ativo e projeto coincidente com o frontend. Login local e `/auth/me`
continuaram respondendo 200 para a mesma identidade interna. PostgreSQL, Redis
e Worker não foram recriados. A cópia original no working tree foi removida.

A credencial não estava staged nem em branches/refs remotos inspecionados.
Foi detectada em um snapshot **local** automático do Codex em refs auxiliares
do Git: mover/ignorar o arquivo não elimina esse objeto. Não houve limpeza
destrutiva das refs ou garantia de apagamento seguro. Esse cache local merece
tratamento pelo operador; rotação/revogação é a opção de invalidar cópias antigas
caso o ambiente/cache tenha sido compartilhado. Não publicar refs auxiliares.

As imagens relacionadas inspecionadas eram anteriores à chegada do arquivo;
não havia cópia no filesystem das imagens ativas API/Worker. Isso não constitui
auditoria de registros externos ou backups históricos desconhecidos.
Login interativo Google, token Google real em `/auth/me` e vinculação legada
continuam pendentes de interação do operador; a consulta Admin não os substitui.
O navegador integrado não conectou nesta sessão, e não havia Playwright/Edge
local disponível: não houve inspeção visual do botão ou popup Google. A
configuração servida está coerente e os testes de exibição do botão passaram.

Regressões desta ativação: 40 testes backend de autenticação/SDK/identidade e
30 testes frontend de configuração/login/vinculação passaram. Build API
descartável com canário sintético confirmou que ADC, `.env.firebase.local` e
objetos `.git` são excluídos da imagem. Comparação em memória não detectou
segredos administrativos nos logs de API/Worker/frontend nem no bundle servido.
O canário foi removido; nenhuma credencial real foi usada no build ou nos testes.

**Impacto existente da ativação:** login local continua funcionando, mas novo
cadastro local deixa de ser permitido quando Firebase está habilitado. Só ative
depois de preparar o caminho Google para não bloquear novos cadastros.

## Homologação real ainda necessária

Após configuração, confirme `/auth/config` com flag ativa e projeto esperado,
e o botão Google visível. Faça uma entrada Google real, confirme a resolução
do mesmo usuário interno em entradas repetidas, refresh, logout, retorno ao
contexto anterior e isolamento entre duas contas de teste.

Para uma conta legada com mesmo e-mail, o primeiro login Google deve retornar
conflito, não assumir ownership. Entre pela senha local e use a ação explícita
de vincular Google, com senha novamente e prova Google recente. Confirme que
plano, transcrições, reuniões e BYOK continuam associados ao mesmo `users.id`.
Não registre tokens, senhas, e-mails pessoais ou conteúdo dos recursos como
evidência. Registre apenas resultados sanitizados e identificadores de testes.

## Validação automatizada desta etapa

Testes com mocks cobrem tokens válidos, inválidos, expirados/revogados,
configuração desabilitada, usuários novos/existentes, conflito de e-mail,
vinculação com prova recente, isolamento, planos, Guest e sessão/contexto.
O frontend valida aliases, precedência, configuração inválida e exclusão de
canários de segredos administrativos do bundle. Integração PostgreSQL/Redis/RQ
usa serviços descartáveis, não o banco de desenvolvimento.

Resultado local: **514 testes backend passaram**, dois testes de mídia foram
ignorados por ausência de FFmpeg na imagem de testes; o módulo de filtro que
carrega ML ficou fora da coleta, conforme a política existente do CI.
**231 testes frontend passaram**, lint e build passaram. Alembic upgrade/check,
pip check, compilação Python com cache temporário, Compose base/overlay e build
Docker frontend passaram. A primeira compilação tentou gravar no mount somente
leitura e falhou; foi repetida corretamente com cache no container descartável.
O CI instala FFmpeg e deve repetir as validações sobre o SHA final do PR.

Docker pode emitir `SecretsUsedInArgOrEnv` pelo nome de API_KEY/AUTH_DOMAIN.
Neste caso são campos públicos do Firebase Web, não chaves administrativas;
isso não autoriza colocar outros segredos em build args.

## Reversão

Desabilitar a flag oculta Google e mantém login local e os dados. Contas criadas
exclusivamente com Google precisam da integração para entrar; não lhes atribua
senhas nem elimine vínculos para forçar rollback. Esta etapa não altera schema.
