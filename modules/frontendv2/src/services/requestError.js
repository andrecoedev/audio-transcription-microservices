// Translate known API failures without changing contracts or exposing diagnostics.
const messages = {
  'File content does not match a supported audio/video format': 'O arquivo não corresponde ao formato indicado. Exporte o áudio novamente como WAV ou MP3; não basta trocar a extensão do nome.',
  'Audio exceeds the public duration limit': 'O áudio ultrapassa o limite de duração. Confira o limite e envie um arquivo mais curto.',
  'AssemblyAI credential unavailable or invalid': 'Não foi possível acessar o AssemblyAI. Confira a conexão do serviço em Configurações; visitantes podem tentar novamente mais tarde.',
  'AssemblyAI quota exceeded': 'A cota do AssemblyAI foi atingida. Confira os limites da conta que fornece o serviço antes de tentar novamente.',
  'AssemblyAI processing timed out': 'O AssemblyAI demorou além do limite para transcrever. Tente novamente mais tarde.',
  'AssemblyAI returned an invalid response': 'Não foi possível ler o resultado do AssemblyAI. Tente novamente; se continuar, procure o suporte da USAGI.',
  'AssemblyAI is temporarily unavailable': 'O AssemblyAI está temporariamente indisponível. Tente novamente mais tarde.',
  'Transcription processing failed': 'Não foi possível concluir a transcrição. Tente enviar o áudio novamente.',
  'Audio could not be decoded': 'Não foi possível ler o áudio deste arquivo. Confira se ele contém som e exporte novamente como WAV ou MP3. Se o problema continuar, procure o suporte da USAGI.',
  'Platform transcription budget exhausted': 'A franquia de transcrição da USAGI está esgotada no momento. Tente novamente mais tarde ou consulte as opções da sua conta.',
  'Visitor transcription is unavailable': 'A transcrição para visitantes está indisponível no momento. Tente novamente mais tarde.',
  'Platform transcription is unavailable': 'A transcrição fornecida pela USAGI está indisponível no momento. Confira outras opções em Configurações.',
  'Provider credential storage is unavailable': 'Não foi possível guardar sua chave agora. Tente novamente mais tarde; se continuar, procure o suporte da USAGI.',
  'User provider credential is unavailable': 'Não foi possível usar sua chave salva. Confira a conexão do serviço em Configurações.',
  'Meeting intelligence is not configured': 'O resumo inteligente está indisponível. Confira a conexão do Gemini em Configurações.',
  'Job queue is temporarily unavailable': 'Não foi possível iniciar a transcrição agora. Tente novamente em alguns instantes.',
  'Audio storage is temporarily unavailable': 'Não foi possível guardar seu áudio agora. Tente novamente em alguns instantes.',
  'Unable to create transcription job': 'Não foi possível iniciar a transcrição. Seu arquivo continua selecionado; tente novamente.',
  'Invalid username or password': 'Usuário ou senha incorretos. Confira os dados e tente novamente.',
  'Use Google sign-in to create your account': 'Use Continuar com Google para criar sua conta.',
  'Uploaded file is empty': 'O arquivo está vazio. Selecione outro áudio ou vídeo.',
  'Invalid transcription model': 'Selecione um serviço de transcrição disponível e tente novamente.',
  'Transcription not found': 'Esta transcrição não está disponível. Volte ao Histórico e confira seus arquivos.',
  'Transcription job not found': 'Esta transcrição não está disponível. Volte ao Histórico e confira seus arquivos.',
  'Authentication service temporarily unavailable': 'Não foi possível verificar sua sessão agora. Tente novamente em alguns instantes.',
  'Authentication service unavailable': 'O acesso à conta está indisponível no momento. Tente novamente mais tarde.',
}

export function requestErrorMessage(status, detail) {
  if (typeof detail === 'string' && messages[detail]) return messages[detail]
  // Keep actionable Portuguese policy messages provided by the API. Never return
  // unknown internal/provider diagnostics, validation payloads or request config.
  if (typeof detail === 'string' && /^(Não |Você |Sua |Seu |O serviço |A transcrição |Limite |Muitas )/.test(detail)) return detail
  const byStatus = {
    400: 'Não foi possível aceitar os dados enviados. Confira os campos e tente novamente.',
    401: 'Sua sessão não é mais válida. Entre novamente para continuar.',
    403: 'Sua conta não pode realizar esta ação. Confira as opções disponíveis em Configurações.',
    404: 'Este conteúdo não está disponível. Volte à lista e tente novamente.',
    409: 'Este conteúdo mudou ou está em processamento. Atualize a página antes de tentar novamente.',
    413: 'O arquivo ultrapassa o limite de envio. Confira o tamanho permitido e selecione outro arquivo.',
    415: 'Este formato de arquivo não é aceito. Selecione um dos formatos indicados na tela.',
    422: 'Confira os campos e o formato do arquivo antes de tentar novamente.',
    429: 'Muitas solicitações em pouco tempo. Aguarde um pouco antes de tentar novamente.',
    502: 'O serviço está temporariamente indisponível. Tente novamente em alguns instantes.',
    503: 'O serviço está temporariamente indisponível. Tente novamente em alguns instantes.',
    504: 'O serviço demorou para responder. Confira o estado da transcrição antes de enviar novamente.',
  }
  return byStatus[status] || (status == null
    ? 'Não foi possível conectar ao serviço. Verifique sua conexão e tente novamente.'
    : 'Não foi possível concluir a solicitação. Tente novamente; se continuar, procure o suporte da USAGI.')
}
