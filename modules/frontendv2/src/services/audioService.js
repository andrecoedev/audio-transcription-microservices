import api from './api'

export const audioService = {
  // Verificar saúde do backend
  async checkHealth() {
    const { data } = await api.get('/health')
    return data
  },

  // Upload e criação de job assíncrono local
  async createTranscriptionJob(file, options = {}) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('use_diarization', options.useDiarization || false)

    if (options.transcriptionModel) {
      formData.append('transcription_model', options.transcriptionModel)
    }

    const { data } = await api.post('/transcriptions/jobs', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: options.onUploadProgress,
    })

    return data
  },

  // Consultar status de job assíncrono
  async getTranscriptionJobStatus(id) {
    const { data } = await api.get(`/transcriptions/jobs/${id}/status`)
    return data
  },

  // Listar transcrições
  async listTranscriptions(params = {}) {
    const { data } = await api.get('/transcriptions', { params })
    return data
  },

  // Obter detalhes de uma transcrição
  async getTranscription(id) {
    const { data } = await api.get(`/transcriptions/${id}`)
    return data
  },

  // Deletar transcrição
  async deleteTranscription(id) {
    const { data } = await api.delete(`/transcriptions/${id}`)
    return data
  },

  // Obter estatísticas
  async getStats() {
    const { data } = await api.get('/stats')
    return data
  },

  // Obter status das API Keys (sem expor valores completos)
  async getApiKeysStatus() {
    const { data } = await api.get('/api-keys')
    return data
  },

  // Atualizar API Keys
  async updateApiKeys(keys) {
    const { data } = await api.post('/api-keys', {
      hf_token: keys.hfToken || null,
      aai_api_key: keys.aaiApiKey || null,
      gemini_api_key: keys.geminiApiKey || null,
    })
    return data
  },

  // Gerar ata de reunião
  async generateMeetingMinutes(transcriptionId, meetingData) {
    const { data } = await api.post('/meeting-minutes/generate', {
      transcription_id: transcriptionId,
      title: meetingData.title,
      date: meetingData.date,
      participants: meetingData.participants,
      meeting_context: meetingData.context,
    })
    return data
  },

  // Verificar status do gerador de atas
  async getMeetingMinutesStatus() {
    const { data } = await api.get('/meeting-minutes/status')
    return data
  },

  async getSystemGpu() {
    const { data } = await api.get('/system/gpu')
    return data
  },

}
