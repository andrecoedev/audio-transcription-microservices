# Evidência visual da Central Admin

Playwright MCP, desktop 1440 × 1000 e mobile 390 × 844. Imagens inspecionadas
pelo responsável pela integração e por verificador independente.

- [Visão geral desktop](desktop-overview.png)
- [AssemblyAI desktop](desktop-assemblyai.png)
- [Visão geral mobile](mobile-overview.png)
- [Confirmação mobile](mobile-confirmation.png)

Ambiente descartável com API HTTP real, PostgreSQL e Redis isolados, contas
`example.invalid` sintéticas, sem credenciais externas. Beta e uso da plataforma
permaneceram desativados. Os números exibidos são cenários de teste, não uso
real nem configuração de uma rodada em produção.

Foram exercitados salvamento e refresh, conflito de versão com rascunho
preservado, convite/revogação exclusivamente sintéticos e confirmação por
teclado (Tab, Shift+Tab, Escape e restauração de foco). Não foi observado overflow
horizontal no documento ou no conteúdo principal nas duas larguras.

O único erro de rede observado no fluxo de conflito foi o HTTP 409 provocado
deliberadamente; não houve erro JavaScript inesperado. Nenhuma chamada ao
AssemblyAI ou outro provider foi realizada para produzir estas imagens.
