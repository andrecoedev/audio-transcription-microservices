# Frontend USAGI

React 18, React Router 7, Vite 8, Tailwind, Zustand, Axios, Lucide, Dropzone
e React Hot Toast. Versões exatas são as do package-lock.json.

## Executar e validar

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
[operações](../../docs/operations.md). Vite usa porta 3000; build vai para dist
(ignorado). nginx.conf permanece como configuração opcional de hosting SPA;
não há serviço frontend Docker no Compose suportado.

## Fluxos

App.jsx valida a sessão com /auth/me e protege rotas; falha da API não cria sessão
anônima. authStore guarda sessão/logout. api.js centraliza HTTP/erros.
audioService.js mantém contratos de upload/jobs/polling/resultados/reuniões/
intelligence. Pages usam serviços e estado React; hooks/store de transcrição
sem consumidores foram removidos, sem mudar UX.

Rotas: login, dashboard, transcriptions e detalhe, meetings e detalhe,
new-transcription, meeting-minutes e settings. O fluxo antigo meeting-minutes
ainda está ativo na Sidebar; não foi removido sem decisão de compatibilidade.
Settings consulta flags de configuração, nunca recebe/persiste chaves.

flow.test.jsx protege login, rotas, upload/polling/resultado/exclusão e erros.
MeetingIntelligencePanel.test.jsx protege falha/retry e revisão anterior durante
regeneração. audioService.test.js protege URLs/contratos.

Guias duplicados com demo user, CORS wildcard, Vite 5 e arquivos inexistentes
foram substituídos por esta documentação. Sem redesign ou nova funcionalidade.
