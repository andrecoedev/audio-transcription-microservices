import api from './api'

const base = '/admin/settings'

export const adminSettingsService = {
  getSettings: async () => (await api.get(base)).data,
  getOverview: async () => (await api.get(`${base}/overview`)).data,
  getParticipants: async () => (await api.get(`${base}/participants`)).data,
  searchAccounts: async (query) => (await api.get(`${base}/accounts`, { params: { q: query } })).data,
  getHistory: async () => (await api.get(`${base}/history`)).data,
  initialize: async (version) => (await api.post(`${base}/initialize`, { version, confirmed: true })).data,
  save: async (section, version, confirmed, changes) => (await api.patch(`${base}/${section}`, {
    version, confirmed, ...changes,
  })).data,
  grant: async (userId, roundId, expiresAt) => (await api.post(`/admin/accounts/${userId}/beta`, {
    capabilities: ['transcription.platform'], round_id: roundId, expires_at: expiresAt,
  })).data,
  revoke: async (userId, grantId) => (await api.delete(`/admin/accounts/${userId}/beta/${grantId}`)).data,
}
