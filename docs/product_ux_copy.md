# UX e linguagem do produto

Segunda entrega visual após o PR #31, baseada em
`origin/dev@efe8d504590ad7ad02b19b0f100a800166b066f9`.
[Card de aceite e execução](https://trello.com/c/wbi39LT2).
Esta documentação descreve a interface; não altera a política do Beta.

## Direção e limites

Voz clara, direta e orientada à ação. A interface explica próximo passo,
estado real e consequências, sem transformar limitações em promessas.
“Transcrição”, “Reunião”, “Resumo inteligente”, “Decisões”, “Tarefas”,
“Detecção de falantes” e “Sua própria chave” são os termos preferidos.

A [fundação visual](design_system_shell.md) continua sendo a fonte de tokens,
Geist, marca provisória, superfícies, controles e foco. Não há nova fonte,
logo, mascote, design system ou dependência. As capturas usam apenas fixtures,
nunca dados de usuários nem saldo real.

Não há mudança de autenticação, grants, planos, franquias, orçamento, providers,
BYOK, Worker/RQ, persistência, ownership ou contrato HTTP. Nenhuma migration.

## Telas e hierarquia

- Home: próximo passo, transcrições/reuniões e atividade recente em lista;
  sem upload duplicado, métricas decorativas ou tarefas inventadas.
- Acesso: título neutro “Entrar”; cadastro informa que não concede Beta.
  O rodapé não presume uma transcrição anterior.
- Demonstração: “Dados de exemplo”, explicitamente sem áudio do visitante.
- Envio: “Transcrição do Beta” e “Minha chave de transcrição”; AssemblyAI
  identificado no contexto. Seleção e indisponibilidade continuam reais.
  Automático não seleciona a franquia Beta.
- Histórico: ausência inicial, busca e filtro vazios têm mensagens distintas.
  Nomes originais, títulos manuais, números pt-BR e paginação preservados.
- Reunião: leitura em 17 px, itens com divisores e menos caixas aninhadas;
  evidências mantêm IDs/âncoras. Serviço/modelo/revisão em “Sobre esta versão”.
  Revisão humana e informação de envio externo continuam visíveis.
- Tarefas: sugestões, aceitas e descartadas continuam distintas.
- Configurações: mensagens curtas, chaves write-only e custo da própria conta
  preservados. Local indisponível não pede uma conta externa inexistente.
- Admin: linguagem operacional; confirmação e CAS/versionamento preservados.
  Valores financeiros continuam restritos à área administrativa.

## Copy: antes e depois

| Contexto | Antes | Depois |
|---|---|---|
| Guard de conta | Texto presumindo transcrição anterior | Entre para continuar |
| Guest | Demonstração sintética | Dados de exemplo |
| Chave própria no envio | AssemblyAI como opção principal | Minha chave de transcrição |
| Navegação | Exportar transcrição | Abrir transcrição |
| Pesquisa textual | Buscar no áudio | Buscar na transcrição |
| Acesso à reunião | Ver reunião estruturada | Abrir reunião |
| Resumo ausente | Ainda não há análise desta reunião | Esta reunião ainda não tem resumo |
| Decisões vazias | Nenhum item identificado | Nenhuma decisão identificada nesta versão |
| Perguntas vazias | Mensagem genérica | Nenhuma pergunta em aberto identificada |
| Tarefa persistida | Descartar | Marcar como descartada |
| Credencial | Chave salva com segurança | Chave salva |
| Consumo | Uso com credenciais próprias (BYOK) | Uso com sua própria chave |

## Estados e causas reais

`requestError.js` traduz causas conhecidas, não deduz orçamento pelo status HTTP.
O mesmo 429 pode representar rate limit, fila, concorrência ou franquia.
Detalhes desconhecidos continuam sanitizados pelo tratamento existente.

| Causa | Mensagem/estado visível |
|---|---|
| Seleção de arquivo | Arquivo selecionado; não confirma envio |
| Upload | Enviando arquivo… |
| queued | Áudio recebido. Aguardando processamento |
| processing | Seu áudio está sendo processado. Você pode voltar depois para acompanhar |
| completed | Transcrição concluída. Abra a reunião para revisar o conteúdo |
| failed | Falha segura com orientação de novo envio; não confunde com silêncio |
| Polling falhou | Aviso de falha de atualização; último estado conhecido preservado |
| Franquia da rodada esgotada | Você atingiu a franquia desta rodada do Beta. Não há renovação automática |
| Plataforma indisponível | Novas transcrições do Beta estão temporariamente indisponíveis. Tente novamente mais tarde |
| Rate limit | Orientação para aguardar, sem afirmar esgotamento de franquia |
| Concorrência | Aguardar uma transcrição terminar antes de novo envio |
| Armazenamento cheio | Excluir arquivos desnecessários antes de novo envio |
| Redis indisponível | O serviço está temporariamente indisponível. Tente novamente em alguns instantes |
| Concluído com segmentos vazios | Nenhuma fala foi identificada neste áudio |
| Busca sem correspondência | Nenhum trecho corresponde à busca |

Detalhe e workspace só afirmam ausência de fala com estado `completed` e lista
vazia. Processamento incompleto não é silêncio. Isso descreve o resultado,
não garante qualidade acústica do detector. Sem percentual/estimativa inventados.
Exclusão continua comunicando `cleanup_pending`, sem prometer desfazer,
limpeza imediata ou remoção de cópias de serviços externos.

## Evidências locais — 30/10/2026

Runtime descartável `usagi-ux-20261030`, PostgreSQL `usagi_beta_e2e_test`,
API loopback 2029 e frontend 4180. PostgreSQL/Redis/RQ/FFmpeg reais;
Firebase, transcrição e inteligência simulados nas fronteiras de SDK.
Rede do navegador limitada às duas origens locais. Nenhuma credencial real,
áudio privado, concessão real ou chamada paga. Não homologa produção,
Google real, qualidade ASR, CUDA ou disponibilidade comercial.

| Aceite | Evidência executada pelo responsável |
|---|---|
| AC01 Home/demo/acesso | Playwright: Home distinta, demo explícita, cadastro sem concessão automática |
| AC02 Upload/opções | Jornadas HTTP com upload único, validação real e Beta explícito; testes de seleção/indisponibilidade |
| AC03 Estados/polling | Testes observáveis de fila/processamento/conclusão/falha e atualização falha; jornada RQ real com SDK double |
| AC04 Lista/busca/silêncio | Capturas inicial/busca, concluído vazio e falha; testes de filtro e estado incompleto |
| AC05 Workspace | 200 segmentos no navegador, 500 no teste; links/evidências e tarefa aceita preservados |
| AC06 Acessibilidade | 1440/1280/390 px, sem overflow do documento; setas/Home/End, foco e painel associado |
| AC07 Settings/Admin | Regressões de write-only, salvar/substituir/remover, permissão, CAS e confirmação; capturas desktop/mobile |
| AC08 Consumo | HTTP real 429 para quota zero; 503 para plataforma; Beta desativado não selecionável; rate limit distinto |
| AC09 Jornada | Desktop e mobile: 13 ações, 17 s cada; Guest → cadastro → grant sintético → upload → RQ → resultado → resumo → decisão → tarefa → logout/login/retorno |
| AC10 Segurança/falhas | Outro usuário e Admin receberam 404 em três recursos do titular; Redis bloqueou envio; crash/restart e BYOK em integração PostgreSQL |
| AC11 Evidências | [Galeria sintética](design/product-ux-copy/README.md), scripts e este documento |
| AC12 Qualidade | Frontend/backend, lint/build, Alembic e Docker; CI/gate do HEAD no PR/Trello |

Jornadas desktop/mobile sem erros JS ou respostas HTTP inesperadas.
Quota/plataforma reduzidas **somente na stack descartável**, via Admin real com
CAS/confirmação, restauradas em `finally`. Redis parado bloqueou submissão;
Redis/Worker foram restaurados. Após remover registros RQ das fixtures e reiniciar
API/Worker, resultados continuaram disponíveis no PostgreSQL.

O drill Linux `test_worker_killed_after_submission_and_restarted_never_duplicates_call`
passou na repetição dos três testes verticais. Não homologa crash CUDA ou
reenvio de chamada real. BYOK repetido nos testes de criptografia, isolamento,
resolução e UI. O runtime visual deixa armazenamento de chaves indisponível;
não houve smoke com chave real.

Baseline backend: **644 testes aprovados**, incluindo PostgreSQL/Redis/RQ,
módulo ML excluído como no CI. Os três testes verticais também passaram novamente.
Alembic até `0018` em banco vazio e `check` sem operações pendentes.
A primeira tentativa da baseline falhou por banco sem migrations; após Alembic
no banco descartável, a repetição passou. Não se alterou produção para contornar
erros. A contagem final frontend e os gates do HEAD constam no PR.

Frontend final: **372 testes / 44 arquivos**, lint sem warnings e build aprovado
localmente e na imagem Node 22. Compose e compilação Python passaram; o cache
Python foi redirecionado para `/tmp` porque o código é montado read-only.
Docker avisa sobre os nomes `VITE_FIREBASE_API_KEY`/`AUTH_DOMAIN` nos argumentos
já existentes: são configuração Web pública, não credenciais administrativas;
o build desta entrega não recebeu valores reais. Nenhuma dependência foi atualizada.

## Reprodução

Seguir [o harness E2E](beta_e2e_homologation.md), com projeto Compose novo,
descartável e sem overlays reais ou `.env` do produto.

1. Aplicar Alembic, seed vazio e iniciar API/Worker sintéticos.
2. Iniciar Vite com `homologation/vite.config.js`.
3. Executar `journey.playwright.js` em desktop e mobile.
4. Preparar `tests.homologation.server presentation`.
5. Executar `ux-errors.playwright.js`, `ux-visual.playwright.js` e
   `presentation.playwright.js` via Playwright MCP. Caminhos relativos a
   `modules/frontendv2/homologation/`; CWD das capturas na raiz do repo.
6. Seguir os drills Redis/restart/crash; restaurar serviços mesmo em falha.
   Não rodar pytest no banco usado para walkthrough.

`ux-errors` recusa projeto Firebase/rodada/admin distintos das fixtures.
`ux-visual` aguarda dados, verifica overflow e tabs por teclado.
O storage do Firebase double é apenas de teste, não a sessão do produto.

## Findings e limitações

- **P0/P1:** nenhum finding novo confirmado.
- **P2 corrigidos:** quota confundida com plataforma/rate limit; ausência de fala
  sem mensagem; tabs incompletas; rótulo de exportação que navega;
  orientação incorreta para conectar uma conta de processamento local.
- **P3 preservados:** IDs técnicos de falantes até renomeação; histórico com scroll
  interno; bundle acima de 500 kB e deprecações backend. Sem mudança de pipeline,
  dependências ou chunking neste recorte.
- Toasts globais preexistentes podem cobrir temporariamente parte do conteúdo
  mobile; as capturas full-page preservam sua posição na viewport. Não houve
  mudança de posição nem perda permanente de conteúdo. Favicon definitivo
  continua pendente na fundação.
- Sem certificação WCAG, leitor de tela, celular físico ou inferência real.
  Contraste usa os tokens já testados da fundação.
- Google real, BYOK real, serviços pagos e implantação não foram acionados.

A revisão independente de especificação apontou silêncio no workspace;
corrigido com testes de concluído vazio e processamento incompleto.
A revisão de padrões não encontrou violação acionável.
O verificador funcional independente confirmou resumo/evidências, tarefas
sugeridas e aceitas, tabs Home/End, 200 segmentos em scroller mobile,
silêncio distinto de busca vazia e Settings carregado. Não repetiu gravações
Admin/BYOK, ownership HTTP, polling falho ou os drills de infraestrutura;
esses itens foram executados pelo responsável e pela suíte de integração,
não apresentados como execução independente.
