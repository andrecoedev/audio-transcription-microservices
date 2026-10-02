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

  async listMeetings(params = {}) {
    const { data } = await api.get('/meetings', { params })
    return data
  },

  async getMeeting(id) {
    const { data } = await api.get(`/meetings/${id}`)
    return data
  },

  async getMeetingTranscript(id) {
    const { data } = await api.get(`/meetings/${id}/transcript`)
    return data
  },

  async updateMeetingTitle(id, title) {
    const { data } = await api.patch(`/meetings/${id}`, { title })
    return data
  },

  async renameMeetingSpeaker(id, speakerId, displayName) {
    const { data } = await api.patch(`/meetings/${id}/speakers/${encodeURIComponent(speakerId)}`, {
      display_name: displayName,
    })
    return data
  },

  async deleteMeeting(id) {
    const { data } = await api.delete(`/meetings/${id}`)
    return data
  },

  async getMeetingActions(id) {
    const { data } = await api.get(`/meetings/${id}/actions`)
    return data
  },

  async createMeetingAction(id, payload) {
    const { data } = await api.post(`/meetings/${id}/actions`, payload)
    return data
  },

  async updateMeetingAction(id, actionId, payload) {
    const { data } = await api.patch(`/meetings/${id}/actions/${actionId}`, payload)
    return data
  },

  async deleteMeetingAction(id, actionId) {
    await api.delete(`/meetings/${id}/actions/${actionId}`)
  },

  async requestMeetingIntelligence(id, regenerate = false) {
    const path = `/meetings/${id}/intelligence${regenerate ? '/regenerate' : ''}`
    const { data } = await api.post(path)
    return data
  },

  async getMeetingIntelligenceStatus(id) {
    const { data } = await api.get(`/meetings/${id}/intelligence/status`)
    return data
  },

  async getMeetingIntelligenceResult(id) {
    const { data } = await api.get(`/meetings/${id}/intelligence/result`)
    return data
  },

  async getSystemGpu() {
    const { data } = await api.get('/system/gpu')
    return data
  },

}
