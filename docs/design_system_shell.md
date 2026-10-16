# Fundação visual e shell

PR 1 da evolução visual, base `origin/dev@31d3ea4` (PR #30 integrado),
observado em 16/10/2026. [Entrega no Trello](https://trello.com/c/Xwts0sBS).
O React funcional permanece como base; o design-lab é referência de direção,
não uma implementação a portar. PR 2 (páginas e copy) não está incluído.

## Antes × depois

| Superfície | Antes | Depois |
|---|---|---|
| Identidade | Nome/título dispersos, emoji e favicon Vite | Configuração `src/brand.js`, título `USAGI — Transcrição`, wordmark textual sem símbolo |
| Tipografia | Pilha do sistema e metadados de 11/12 px | Geist variável local, UI 14–16 px, metadados 13 px, fallback japonês do sistema |
| Shell | Branco, sidebar 220 px, menu mobile sem confinamento de foco | Neutro esverdeado, sidebar desktop 236 px, menu compacto 220 px com foco e fundo inerte |
| Navegação | Histórico depois de Reuniões | Minhas transcrições antes de Reuniões, mesma rota `/transcriptions` |
| Componentes | Valores visuais dispersos | Tokens de cores/espaços/raios, controles com estados coerentes e badges discretos |
| Administração | Separação homologada no PR #30 | Mesma condição/rota, preservada e exercitada em desktop/mobile |

Antes: [workspace desktop](design/beta-e2e/workspace-desktop.png),
[workspace mobile](design/beta-e2e/workspace-mobile.png),
[Admin desktop](design/admin-beta-settings/desktop-overview.png).
São evidências históricas sintéticas da base, não screenshots pixel a pixel do
mesmo estado. Depois: [galeria e dimensões](design/design-system-shell/README.md).

Não foram redesenhados profundamente Home, upload, workspace, Settings ou Admin.
Cards específicos dessas páginas ainda existem; removê-los indiscriminadamente
mudaria a composição fora do escopo. Bordas úteis continuam separando conteúdo.

## Tokens e componentes

Fonte única: `modules/frontendv2/src/styles/tokens.css`. Tailwind mantém aliases
`primary-*`/`gray-*` para as páginas atuais, evitando uma reescrita de classes.
Novos componentes devem preferir os significados semânticos.

| Token | Valor |
|---|---|
| canvas / shell | `#F7FAF8` / `#EFF4F1` |
| surface / surface-secondary / hover | `#FFFFFF` / `#F4F8F6` / `#E9EEEC` |
| primary / primary-hover | `#1F4939` / `#13382A` |
| primary-soft / tint / mid | `#E2F3E9` / `#CFE5D8` / `#9DBDAA` |
| ink / text-secondary / muted | `#18201C` / `#414A46` / `#626A66` |
| border / control-border | `#DFE4E2` / `#849189` |
| success / soft | `#1E5A3C` / `#E5F3EB` |
| warning / soft | `#7C5019` / `#FBF3DF` |
| danger / hover / soft | `#AC312C` / `#8D2824` / `#FCECE9` |
| info / soft | `#225984` / `#EAF3FA` |
| on-primary | `#FFFFFF` |

Espaços: 4, 8, 12, 16, 24, 32, 48 px. Controles 8 px de raio, cards 10 px,
modais 12 px, badges 6 px. Sombra discreta apenas para sobreposições/popovers;
cards compartilhados sem sombra. Transição 160 ms, reduzida por preferência do
sistema. Sem tema escuro nem animações decorativas novas.

Button mantém submit/disabled/loading, tamanhos mínimos 36/40/44 px e variante
destrutiva. Card usa padding 16/24 px. PageHeader usa 28 px. StatusBadge preserva
labels/fallback, com cor semântica e texto. HelpPopover preserva interação,
posicionamento e Escape; alvo de 32 px. Inputs têm borda de controle mais forte,
focus visível e estado disabled. Timestamps/números tabulares usam a fonte UI.

## Tipografia e marca

Geist variável, local, 69.760 bytes, sem nova dependência npm. Copyright/OFL 1.1,
origem e SHA-256 em [proveniência](../modules/frontendv2/public/fonts/geist/README.md).
O binário upstream não foi modificado; a cópia textual da licença remove somente
espaços no final de linha. Fonte com `font-display: swap`, seguida de fontes do
sistema. A OFL acompanha a distribuição em `public/fonts/geist/OFL.txt`.

Geist cobre o texto PT-BR; não se presume cobertura japonesa. `lang="ja"` usa
Yu Gothic/Hiragino/Noto Sans JP quando instaladas, depois sans-serif. `うさぎ`
foi inspecionado no Chromium local, legível e sem cápsula. Sem download remoto
de fontes. Source Serif 4 não foi adicionada: leitura longa será avaliada no PR 2.

`brand.js` define company, jp, product, descriptor e título derivado. `Brand`
compartilhado é usado na Sidebar/Navbar. Modo compacto omite só o produto.
Teste cobre título e variante compacta; o produto pode mudar num ponto único.
Vite e entrada React aplicam o título derivado. O favicon Vite foi removido;
favicon definitivo permanece pendente, sem criar logo/mascote improvisado.

## Responsividade e acessibilidade

Playwright MCP/Chromium: 1440 × 1000, 1280 × 900, 390 × 844. Sem overflow
horizontal do documento nas superfícies capturadas. A tabela de histórico
mantém scroll horizontal interno, intencional para preservar suas colunas.
Sidebar desktop rola verticalmente; drawer mobile limitado à viewport e rolável.

Menu: foco inicial dentro do dialog; Tab/Shift+Tab confinados mesmo com a área
da conta aberta; Escape/fechar/fundo restauram foco no gatilho; destino move foco
ao conteúdo; resize para desktop remove dialog, inert e scroll lock. Background
inerte e escurecido, botão de fechar dentro do dialog. Estado ativo usa peso,
fundo e `aria-current`, não somente cor. Ícones decorativos ficam ocultos de AT.

Teste automatizado de contraste: 11 pares de texto normal ≥4,5:1 e borda de
controle/surface ≥3:1. Não equivale a certificação WCAG de todas as páginas.
Validação básica de teclado/foco, não auditoria com leitor de tela ou celular
físico. Controles antigos específicos de páginas não foram reescritos.

## Execução e evidências

Ambiente: `usagi-shell-20261016`, banco descartável `usagi_beta_e2e_test`, API
2029, frontend 4180, PostgreSQL/Redis/RQ/FFmpeg reais. Firebase/ASR/inteligência
simulados nas fronteiras de SDK. Nenhum `.env` real, conta pessoal, áudio privado,
grant real ou chamada paga. A fixture ativa políticas exclusivamente sintéticas;
o estado “Beta ativo” das imagens não representa ativação do ambiente do produto.

Reprodução: seguir [harness E2E](beta_e2e_homologation.md), com um projeto Compose
descartável exclusivo. Não combinar com overlays reais nem apontar testes ao
banco do produto. Executar journey em desktop, depois mobile, preparar
`tests.homologation.server presentation`, e executar
`modules/frontendv2/homologation/shell.playwright.js` pelo Playwright MCP.
O script limita rede às duas origens locais e captura a galeria desta entrega.

- Baseline backend: 644 testes passaram, 26 warnings; PostgreSQL/Redis isolados,
  incluindo migrations e integrações. Módulo de filtro ML excluído como no CI;
  sem alegação de inferência CUDA/ASR real.
- Jornada desktop: 13 ações, 46 s; mobile: 13 ações, 40 s; cadastro sem grant
  automático, upload único, resultado, resumo/decisão/tarefa, refresh, logout,
  login e retorno ao contexto. Zero erros JS/rede nas duas jornadas.
- Apresentação: 200 segmentos preservados, falha segura e sessão expirada/
  reautenticação exercitadas; Google apenas simulado, sem concessão implícita.
- Shell: 11 screenshots, três larguras, navegação e foco exercitados.
- Lint/build e suíte frontend completa repetidos após integração; resultados
  finais, CI e Security Gate registrados no PR e Trello do HEAD entregue.
- Aviso de bundle >500 kB preexistente permanece; sem alterar chunking ou
  dependências fora do escopo.

## Findings preservados para PR 2

Já observados na auditoria anterior, sem correção funcional silenciosa:

- “Exportar transcrição” no workspace navega para a transcrição; “Buscar no áudio”
  pesquisa texto, não áudio. Revisar copy/comportamento no recorte apropriado.
- Mensagens de cota/budget/rate limit ainda podem confluir; exigir causa específica.
- Resultado silencioso não apresenta mensagem explícita de nenhuma fala.
- Tabs específicas de páginas ainda precisam revisar navegação por teclado.
- Título longo do detalhe pode quebrar no meio da palavra para acomodar ações;
  priorização das ações/título pertence ao redesign dessa página.
- A duplicação de caixas/pills específica de páginas não foi eliminada neste PR.

Nenhuma mudança em autenticação, ownership, providers, BYOK, plano, grants,
quota/budget, upload, Worker/RQ, endpoints ou schema. Nenhuma migration nova.
