# Frontend USAGI

React 18, React Router 7, Vite 8, Tailwind, Zustand, Axios, Lucide, Dropzone
e React Hot Toast. Versões exatas são as do package-lock.json.

## Iniciar a aplicação completa

Na raiz do repositório, com `modules/backend/.env` configurado:

```powershell
docker compose -p usagidev --env-file modules/backend/.env up --build -d
```

Abra http://localhost:3000. A imagem frontend compila com Node 22 e serve o
React via Nginx. A API é acessada pelo mesmo host em `/api`; o proxy interno
encaminha para o serviço `api`. Nenhuma chave é enviada ao build do frontend.

## Desenvolvimento local e validação

Da raiz do repositório:
```powershell
cd modules/frontendv2
npm ci
npm run dev
npm run test
npm run lint
npm run build
```

Node deve atender engines do Vite instalado; não usar o antigo requisito Node 18.
VITE_API_URL configura somente a URL pública da API, padrão localhost:2020.
Nenhum secret/provider key pode ser colocado no frontend ou em variável VITE_*.

O backend/Redis/Worker/PostgreSQL devem estar ativos conforme
[operações](../../docs/operations.md). O Vite local usa porta 3000 e a API
diretamente em localhost:2020; build vai para dist (ignorado). O Compose da
raiz também inclui o frontend Docker.

## Fluxos

App.jsx valida a sessão com /auth/me e protege rotas; falha da API não cria sessão
anônima. authStore guarda sessão/logout. api.js centraliza HTTP/erros.
audioService.js mantém contratos de upload/jobs/polling/resultados/reuniões/
intelligence. Pages usam serviços e estado React; hooks/store de transcrição
sem consumidores foram removidos, sem mudar UX.

Rotas: entrada pública/guest, signup, login, dashboard, transcriptions e detalhe, meetings e detalhe,
new-transcription, meeting-minutes e settings. O fluxo antigo meeting-minutes
ainda está ativo na Sidebar; não foi removido sem decisão de compatibilidade.
Settings consulta `/health` (banco, Redis, presença do Worker e flags públicas),
nunca recebe/persiste chaves. Configurado não significa modelo carregado nem
provider externo operacional. O diagnóstico CUDA pertence aos logs do Worker.

O link Informações → Status do Sistema abre Settings; não existem páginas
globais de Modelos Ativos ou Falantes. Os falantes são editados na própria
reunião. Não apresentar botões sem destino para essas páginas inexistentes.

Históricos usam `skip/limit/total` da API. A busca por filename é **nesta página**,
não busca global. Falha de consulta é diferente de lista vazia e oferece retry.
Uploads rejeitados têm feedback; copiar/TXT/SRT só são habilitados para resultado
concluído com segmentos. JSON pode exportar os metadados de qualquer estado.

## Limitações de produto

A entrada usa a mesma interface sem exigir login: Guest terá AssemblyAI limitado
(indisponível até recuperação/homologação P4-04, sem fallback local), com resultado
temporário isolado. Signup/login permitem salvar mediante prova Guest validada
pelo servidor. Contas públicas não recebem credenciais externas USAGI; BYOK
completo ficará nas próximas Tasks. Veja [Guest e contas](../../docs/guest_and_accounts.md).
O perfil em Settings é apenas local e pode ser substituído pela identidade retornada em
`/auth/me`; não é preferência persistente de conta nem muda a identidade no
servidor. A escolha de transcrição/diarização é por job, não uma preferência
de conta. Automatic ainda não existe na UI. AssemblyAI possui adapter e caminho
no Worker, mas ainda precisa de validação de erros/capabilities antes de
homologar suporte completo. Não restaurar inputs de secrets antigos de Settings.

Atas legadas mantêm URL/contrato para compatibilidade, mas são temporárias,
não passam pela revisão humana de tarefas e não possuem a persistência/proveniência
de Meeting Intelligence. A experiência recomendada é Reuniões → análise →
ações revisadas → ata consolidada. O antigo campo Contexto adicional não era
repassado pelo backend e não é mais apresentado como funcional.

flow.test.jsx protege login, rotas, upload/polling/resultado/exclusão e erros.
MeetingIntelligencePanel.test.jsx protege falha/retry e revisão anterior durante
regeneração. audioService.test.js protege URLs/contratos.
functional-audit.test.jsx protege navegação/status, falhas/retry/paginação,
upload rejeitado, export sem resultado, labels de login e atualização da ata
quando uma revisão Intelligence conclui. Esses testes DOM usam serviços
simulados; não substituem walkthrough visual ou homologação de providers reais.
guest-auth.test.jsx protege entrada pública, cadastro, expiração, claim explícito
e a ausência de providers pagos para contas públicas.

Guias duplicados com demo user, CORS wildcard, Vite 5 e arquivos inexistentes
foram substituídos por esta documentação. Sem redesign ou nova funcionalidade.
