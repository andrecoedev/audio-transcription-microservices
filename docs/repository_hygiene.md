# Higiene do repositório

O estado versionado deve conter produto atual, testes permanentes, fixtures
necessárias, configuração suportada, migrations aplicadas e documentação por
assunto. Idade/nome do arquivo não prova obsolescência.

Antes de remover, verificar imports, chamadas, descoberta de testes, React,
entrypoints de Worker/CLI, Compose, migrations e documentação. Callbacks
FastAPI/Pydantic e Protocols não são mortos só por não haver chamada textual.

## Artefatos locais

.local-artifacts é a área ignorada de investigação e histórico bruto.
benchmarks/results, áudio/referências gerados, dumps/backups, logs, caches,
database e temp também ficam fora de Git/build context. Não ignorar todos os
JSON/CSV/TXT: manifests, fixtures e requisitos podem ser permanentes.

Resultados completos e ensaios negativos não devem ser apagados para favorecer
uma decisão. Nesta limpeza foram arquivados com a mesma estrutura de paths em
.local-artifacts/archive. Documentação por assunto conserva decisões/métricas/
riscos; originais anteriores também estão no histórico Git 6e2f18d.
O inventário por arquivo desta revisão fica localmente em
.local-artifacts/audit/repository-audit.md, não é uma suíte nem dado de produto.

Não usar git add -f para incluir outputs de novo. Verificar novamente secrets
antes de qualquer push; não imprimir fragmentos ou hashes de credenciais.
Dados privados de SQLite/backups não são artefatos descartáveis: preservar.

## Retidos com ressalva

- Streamlit é entrypoint alternativo legado; consumidores externos não conhecidos.
- meeting-minutes, system/gpu e api-keys possuem consumidores React reais.
- Importador/backup/auditoria legacy são ferramentas operacionais testadas.
- probe_simpleworker é diagnóstico opcional, não runtime; precisa banco vazio.
- Fronteira Pyannote 3/4 pequena permanece no engine e nos testes; candidata
  Docker/pins/resultados foram arquivados, não promovidos.
- Aliases de autenticação/flags antigos permanecem por compatibilidade de imports/
  ambientes; controles privados continuam fail-closed.

Quatro revisions Alembic e toda a suíte de regressão devem ser preservados.
Sem upgrades de dependências nesta revisão; remover apenas declarações sem uso
comprovado, mantendo a matriz Torch/Torchaudio/Torchvision como conjunto.
