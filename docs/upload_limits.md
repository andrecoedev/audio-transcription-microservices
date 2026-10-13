# Limites de upload por conta

O teto técnico global é `MAX_UPLOAD_SIZE_MB`. Contas públicas usam também
`PUBLIC_MAX_UPLOAD_MB`; ser administrador não remove esse limite.

O operador pode conceder uma exceção de tamanho a IDs internos verificados:
`LARGE_UPLOAD_USER_IDS` é uma lista JSON (vazia por padrão) e
`LARGE_UPLOAD_SIZE_MB` define o teto da exceção, no máximo 5120 MiB (5 GiB).
O teto global continua prevalecendo. Configure somente no ambiente da API,
após confirmar o banco e a identidade interna; IDs não são portáveis entre bancos.
Remover o ID da lista revoga a exceção após recriar a API.

Uma configuração local pode ficar em `.env.upload.local` (ignorado pelo Git).
Acrescente `--env-file .env.upload.local` aos demais `--env-file` do comando
Compose, preservando o overlay Firebase. Recrie somente API e frontend após
integrar a mudança; não substitua uma imagem em uso por uma base que retire
funcionalidades de outro PR ainda aberto. Worker, PostgreSQL e Redis não precisam
ser recriados para esta política de upload.

Não use e-mails, roles do cliente ou IDs enviados no upload para conceder acesso.
O backend utiliza a identidade autenticada e retorna `upload_policy` em
`GET /settings/providers`, para a interface apresentar o mesmo teto.
Guest permanece demonstrativo, sem upload real.

A exceção não muda plano, duração, concorrência, rate limits, orçamento,
franquias nem autorização de providers. Uploads grandes continuam exigindo
espaço para multipart temporário, áudio original e conversão. O proxy deve
permitir esse tamanho; não desabilite proteções globais nem aceite tamanho ilimitado.
Os testes usam limites reduzidos para verificar fronteiras sem gerar arquivos de 5 GiB.
