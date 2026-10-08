import api from './api'

export const usageService = {
  async getOverview() {
    const { data } = await api.get('/usage/overview')
    return data
  },
}
