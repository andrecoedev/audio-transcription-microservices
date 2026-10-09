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

O overlay opcional existente monta somente na API um JSON administrativo já
fornecido pelo operador, somente leitura, em
`.local-artifacts/firebase-adminsdk.json`. Não crie um arquivo vazio ou aceite
uma montagem de diretório para contornar sua ausência. Após a preparação:

```powershell
docker compose -p usagidev --env-file modules/backend/.env -f compose.yaml -f modules/backend/docker-compose.firebase.yml up --build -d
```

Em ambientes com ADC gerenciado, use o mecanismo aprovado daquele ambiente,
sem copiar uma chave para o frontend ou Worker. O overlay local não é uma
prescrição para produção.

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
