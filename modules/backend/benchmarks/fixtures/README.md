# Fixtures locais

Coloque aqui, sem versionar, três áudios não sensíveis:

- `short.*`: aproximadamente 1 minuto;
- `medium.*`: aproximadamente 10 minutos;
- `long.*`: entre 30 e 60 minutos.

Use exatamente os mesmos arquivos para os dois engines. A fixture sintética
gerada pelo script pai valida somente decode, inferência e cleanup; silêncio/tom
não serve para afirmar qualidade ou performance de fala real.

Em Docker Desktop/WSL, o benchmark usa o pico total de VRAM da GPU como fallback
quando `nvidia-smi` não informa memória por PID. O JSON registra
`vram_measurement=gpu_total`; compare o delta, não o total absoluto.
