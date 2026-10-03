# P5-01 — Product UI/UX & Design System

## Referência e implementação

As imagens `00.png` a `08.png` são as referências visuais aprovadas. Todas foram
inspecionadas antes da implementação; o conector Figma não foi utilizado.
Os exemplos das referências orientam comportamento e hierarquia, não dados do produto.

| Referência | Tela/comportamento implementado |
| --- | --- |
| 00 | Direção visual e tokens compartilhados |
| 01 | Nova transcrição, upload e atividade recente |
| 02 | Processamento e acompanhamento do job |
| 03 | Workspace, transcrição e evidências |
| 04 | Tarefas revisadas |
| 05 | Reuniões e histórico |
| 06 | Configurações e serviços de IA/BYOK |
| 07 | Autenticação integrada à navegação da aplicação |
| 08 | Estados de credencial e comportamento responsivo |

O frontend usa os contratos existentes de P3/P4, sem novos endpoints, migrations,
providers ou conteúdo fictício. A seção Tarefas reutiliza as tarefas revisadas
da reunião selecionada. Os detalhes antigos de transcrição e atas continuam acessíveis.

## Fundação visual

- Tokens de superfície, borda, texto, raio e verde escuro USAGI em `src/styles/index.css`
  e `tailwind.config.js`; componentes existentes reutilizados.
- `PageHeader`, `StatusBadge`, `ProcessingStatus` e formatadores de data/duração.
- Sidebar consistente, área da conta, navegação móvel, foco visível, skip link,
  estados de loading/error/disabled e preferência de movimento reduzido.
- Workspace com panes limitados e rolagem independente, texto longo quebrável,
  busca e navegação até evidências; empilhamento em telas menores.

## Diferenças intencionais

- Exportação não é formato do áudio. São oferecidos somente os formatos existentes
  ou efetivamente implementados: TXT, SRT, VTT, JSON e as exportações de atas existentes;
  não se promete PDF.
- Sem estimativa inventada de duração nem progresso fictício de inferência. Upload
  mostra progresso de envio; processamento mostra os estados reais do job.
- Tarefas são consultadas por reunião, não como agregação global inexistente na API.
  A busca de Histórico se limita à página carregada; paginação e filtro de status
  continuam no servidor.
- Credencial BYOK salva não significa credencial homologada pelo provider. Preferências,
  disponibilidade e origem de credencial refletem a política real do backend.
  Nenhum secret é devolvido pela UI; inputs são limpos após operações e troca de aba.
- Autenticação mantém usuário/senha e Guest existentes, sem Google Login/Firebase.
  Configuração de perfil local não é apresentada como alteração persistida no servidor.
- Transcrição não ganhou edição de texto inexistente no contrato; título e falantes
  preservam suas ações existentes. Exemplos de hover/edição não viraram registros.
- A pilha de fontes prefere Inter, com fallback do sistema; não foi introduzida
  dependência de download remoto de fonte.

## Comparação visual local

Screenshots em `implemented/` foram produzidas com Chromium headless e respostas
**sintéticas de teste**, sem dados pessoais ou credenciais. A comparação cobriu dez
telas/estados em desktop 1480×1000 e mobile 390×844. O workspace foi exercitado com
500 segmentos e rolagem real; não houve overflow horizontal no viewport móvel testado.
O browser integrado estava indisponível; não se afirma walkthrough manual nele.

| Home | Workspace |
| --- | --- |
| ![Home implementada](implemented/home.png) | ![Workspace implementado](implemented/workspace.png) |

| Mobile | Settings | Processamento |
| --- | --- | --- |
| ![Workspace móvel](implemented/workspace-mobile.png) | ![Settings](implemented/settings.png) | ![Processamento](implemented/processing.png) |

## Validação da entrega

- Frontend: 103 testes em 19 arquivos; lint sem warnings; build Vite aprovado.
- Backend: 263 testes aprovados no projeto Docker isolado `usagip4prefs`, incluindo
  integração PostgreSQL/Redis/RQ com engines simulados; 11 warnings preexistentes.
- Alembic upgrade/check, compilação Python, build Docker frontend, Compose config
  e `git diff --check` aprovados.
- Smoke navegador → API real isolada: signup/login/logout/refresh, preferências,
  upload e criação de job, polling, reunião longa, renomeação de falante, conclusão
  de tarefa, download SRT e exclusão. Conclusão do job foi preparada com resultado
  sintético no PostgreSQL: **não foi executada inferência ML nem chamada paga**.
  O limite público rejeitou tentativas excedentes; apenas contadores sintéticos do
  Redis isolado foram reinicializados para concluir o smoke, sem mudar limites.
- O smoke detectou e corrigiu o envelope incorreto no PATCH de preferências:
  o frontend agora envia os campos no formato já exigido pelo backend. Regressão
  coberta no teste do client, sem alteração da API.
- Gitleaks no histórico da Task sem leaks. Auditoria npm completa encontrou cinco
  apontamentos HIGH na cadeia **dev** Tailwind/braces/chokidar/micromatch/fast-glob,
  preexistente e sem alteração de manifests nesta Task; não realizar major upgrade
  automaticamente. JWT em storage do frontend também permanece decisão preexistente.

Não houve homologação de produção, nova homologação Gemini/AssemblyAI, promoção de
Pyannote 4 ou alteração da matriz ML. Aprovação visual humana no PR continua necessária.
