# Migração para Visual Editorial

A branch `feat/visual-editorial-redesign` parte de `origin/dev` em `53d6a09`. O commit de integração do PR #32, `43045ec`, é ancestral dessa base. O frontend React continua sendo a referência para os fluxos do produto. Os arquivos locais do protótipo ficaram no checkout original.

## Mapeamento das telas

| Tela do protótipo | Tela React | Diferença | Estratégia |
|---|---|---|---|
| Início público | `/`, `Home` e `VisitorHome` | O usuário conectado tem painel e histórico próprios | Landing de sete cenas para visitantes. Painel autenticado mantém links, dados e atividade. |
| Casca do app | `Layout`, `Sidebar`, `Navbar`, `Brand` | Opções reais dependem da sessão e do papel | Lateral de papel, indicador verde, avatar e drawer com foco contido. |
| Nova transcrição | `/new-transcription` após login | Formatos, tetos, serviços e elegibilidade vêm da API | Área de soltar como ação principal, lista de opções, progresso e alertas do produto. |
| Reunião de exemplo | `/new-transcription` para visitantes, `GuestDemo` | O exemplo é identificado e não envia áudio | Ritmo editorial nos trechos, filtro de falante, resumo e salto para evidência. |
| Reunião com duas colunas | `/meetings/:id` | O workspace real também edita título e falantes, busca e expõe a ata | Cabeçalho e metadados em linha, transcrição de leitura e painel de resumo. |
| Resumo, decisões, perguntas, tarefas | Abas do workspace, `MeetingIntelligencePanel` e `MeetingActionsPanel` | Há revisões, ações confirmadas e geração assíncrona | Manter abas de conteúdo, versões, comandos e vínculos originais. |
| Exportar | `/transcriptions/:id` e ata da reunião | Transcrição e ata possuem formatos diferentes | Agrupar TXT, SRT, VTT e JSON em Exportar no detalhe. Comandos de ata ficam no workspace. |
| Sem tela direta | `/login`, `/signup` | Login por e-mail, Google e validação de senha | Tipografia, superfícies, campos e ações compartilhadas. |
| Sem tela direta | `/transcriptions`, `/meetings`, `/tasks`, `/meeting-minutes` | Conteúdo paginado, vazio, em andamento ou com erro | Hierarquia editorial nas páginas e tokens comuns nos controles e estados. |
| Sem tela direta | `/settings`, `/admin/settings` | Formulários, preferências, conectores, uso, acesso administrativo | Manter estrutura dos fluxos e aplicar fundação, cabeçalhos e botões compartilhados. |

## Fundação e decisões

- Papel `#f4f1ea`, lateral `#ece7dc`, superfície `#fbfaf6`, tinta `#1a1e1b`, linhas `#ddd7ca` e verde `#1f4939`. Controles usam borda `#8a8477` para contraste. A linha forte mais clara do protótipo serve como recurso decorativo.
- Shippori Mincho 600 latino hospedado junto ao Geist existente. Os sistemas fornecem a fonte de fallback para caracteres japoneses. [Fonte e licença OFL](https://github.com/google/fonts/tree/main/ofl/shipporimincho)
- A landing tem animações React/CSS de revelação e fios que ligam trechos aos itens de exemplo. O trilho de formatos é rolável à mão e por teclado. Em telas pequenas, a cena de evidências fica em fluxo vertical com os itens visíveis. Com movimento reduzido, o conteúdo fica legível sem a cena fixa.
- O workspace usa texto de 17 px, tempos monoespaçados e divisórias. A busca continua disponível. Abrir uma evidência revela a transcrição no mobile, limpa a busca e foca o trecho do mesmo ID, que recebe destaque.
- O protótipo apresenta decisões e tarefas em uma pilha estática e filtros por falante no workspace. O React mantém navegação por abas, componentes de tarefas reais, busca e edição de falantes. A demonstração preserva seu filtro por falante.
- O upload agrupa avisos, escolha de arquivo e limites efetivos. Botões com `aria-pressed` preservam a escolha exclusiva e as condições de indisponibilidade. A apresentação acompanha o produto quando o limite ou os serviços diferem da referência.
- Firebase e os serviços HTTP continuam ligados às mesmas entradas do produto. A migração não alterou os contratos, implementação de autenticação, regras de negócio, persistência ou dependências npm.

## Comparação visual

Pranchas de Início, Nova transcrição e Workspace com o protótipo, o React de `origin/dev` e o React redesenhado, lado a lado. As capturas de React usam a mesma fixture antes e depois. Na comparação com o protótipo, o estado é equivalente e os dados são sintéticos em ambos. As pranchas foram capturadas com movimento reduzido para estabilizar a composição.

- [Desktop 1440 × 1000](design/visual-editorial/comparacao-1440.png)
- [Notebook 1280 × 900](design/visual-editorial/comparacao-1280.png)
- [Mobile 390 × 844](design/visual-editorial/comparacao-390.png)

Os títulos do Início usam 80 px nos dois desktops e 41,6 px no mobile, iguais aos do protótipo. Nova transcrição e Workspace usam 48/48/32 px nas duas versões. A origem horizontal dos títulos do Início e do Workspace coincidiu nas três larguras. No upload, o título ficou 3 px à direita no desktop e notebook, e na mesma posição no mobile. Seu recuo vertical ficou a cerca de 3 px do protótipo nas três larguras. As quebras de títulos, a altura do cabeçalho de reunião e a densidade do painel diferem com os dados, controles reais e abas. Não houve overflow horizontal no documento React nas larguras verificadas. O histórico preserva rolagem própria na tabela.

## Validação

| Área | Resultado local |
|---|---|
| Frontend | 373 testes em 44 arquivos, lint e build aprovados. O Vite alerta para o chunk principal de 544 kB minificado. |
| Backend | 654 testes no PostgreSQL e Redis isolados, incluindo permissões, ownership, upload, BYOK, franquia e indisponibilidade. A suíte habitual exclui o módulo que importa a pilha de ML. |
| Playwright desktop e mobile | Cadastro, login, logout e retorno ao contexto. Upload sintético real passando pela API e pelo worker em cada resolução. Resumo, decisão e aceite de tarefa persistidos após atualização. |
| Estados e isolamento | HTTP 429 para franquia esgotada e 503 para indisponibilidade, com mensagens distintas. Ausência de concessão implícita no cadastro ou no login simulado por Google. Conta diferente não acessa reunião de outra conta. Conta comum não abre a Central Admin. Sessão expirada retorna à barreira de conta. |
| Workspace | Busca, navegação por setas e End nas abas, foco e destaque na evidência, transcrição longa com 200 trechos, silêncio e falha. Download TXT, SRT, VTT e JSON. |
| Acessibilidade e movimento | 22 estados sem violações detectadas pelo axe-core no conjunto de regras executado. Contorno dos controles com contraste de 3,30:1 sobre papel. Drawer abre pelo teclado e Escape devolve o foco. Cinco fios no último estágio editorial no desktop. Com movimento reduzido, os fios saem e os itens ficam visíveis. |
| CI | O workflow existente **CI baseline** verifica frontend e backend no HEAD do PR para `dev`. O resultado do HEAD fica registrado no PR. |

### Achados e limites

- A primeira execução local do backend usou a origem CORS da pilha de browser. Um teste exige `http://localhost:5173`. A suíte passou com a origem de teste esperada configurada só no container, sem alterar o backend.
- A primeira rodada de acessibilidade apontou rótulo de arquivo, hierarquia dos títulos de cartões e contraste de um texto decorativo. A nova captura e a nova rodada verificaram as correções. A verificação automatizada não substitui a leitura com tecnologia assistiva.
- A revisão de aderência apontou que as contagens da landing podiam ser interpretadas como métricas do produto. Elas passaram a identificar explicitamente os dados da reunião de exemplo.
- Firebase e provedores usam fronteiras simuladas na homologação. O pipeline local exercita armazenamento, autenticação resolvida pelo backend, jobs e revisões. A validação não faz chamadas pagas nem testa contas, chaves ou concessões reais.
- Para validação humana, percorra a landing em desktop e celular. Na área autenticada de teste, confira os estados de upload e navegue entre Transcrição e Resumo inteligente, passando por uma evidência, uma tarefa e uma exportação. Revise o comportamento de teclado e a legibilidade em dispositivo físico.
