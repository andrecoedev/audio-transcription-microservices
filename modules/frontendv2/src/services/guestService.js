import api from './api'

const proof = (token) => ({ headers: { Authorization: `Bearer ${token}` } })

export const guestService = {
  async policy() {
    return (await api.get('/guest/policy')).data
  },
  async createSession() {
    return (await api.post('/guest/sessions')).data
  },
  async session(token) {
    return (await api.get('/guest/session', proof(token))).data
  },
  async createJob(token, file, { onUploadProgress } = {}) {
    const body = new FormData()
    body.append('file', file)
    return (await api.post('/guest/transcriptions/jobs', body, {
      ...proof(token), headers: { ...proof(token).headers, 'Content-Type': 'multipart/form-data' }, onUploadProgress,
    })).data
  },
  async result(token, id) {
    return (await api.get(`/guest/transcriptions/${id}`, proof(token))).data
  },
  async delete(token, id) {
    return (await api.delete(`/guest/transcriptions/${id}`, proof(token))).data
  },
  async claim(token) {
    return (await api.post('/guest/claim', { guest_token: token })).data
  },
}
