import api from './api'

export const usageService = {
  async getPlan() {
    const { data } = await api.get('/account/plan')
    return data
  },
  async getOverview() {
    const { data } = await api.get('/usage/overview')
    return data
  },
}
