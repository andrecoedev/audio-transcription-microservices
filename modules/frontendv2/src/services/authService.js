import api from './api'

export const authService = {
  async signup(username, email, password) {
    const { data } = await api.post('/auth/signup', { username, email, password })
    return data
  },
  async getConfig() {
    const { data } = await api.get('/auth/config')
    return data
  },

  async login(username, password) {
    const { data } = await api.post('/auth/login', { username, password })
    return data
  },

  async me() {
    const { data } = await api.get('/auth/me', { timeout: 10000 })
    return data
  },
}
