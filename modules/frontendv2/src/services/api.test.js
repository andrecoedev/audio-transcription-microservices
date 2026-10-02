import { beforeEach, describe, expect, it } from 'vitest'
import api from './api'
import { useAuthStore } from '../stores/authStore'

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ token: null, user: null, isAuthenticated: false })
})

describe('HTTP credential boundaries', () => {
  it('preserves an explicit Guest proof instead of replacing it with the account JWT', async () => {
    localStorage.setItem('token', 'synthetic-account-proof')
    let authorization
    await api.get('/guest/session', {
      headers: { Authorization: 'Bearer synthetic-guest-proof' },
      adapter: async (config) => {
        authorization = config.headers.Authorization
        return { data: {}, status: 200, headers: {}, config }
      },
    })
    expect(authorization).toBe('Bearer synthetic-guest-proof')
  })

  it.each(['/guest/session', '/transcriptions'])('handles 401 from %s without retaining sensitive error config', async (url) => {
    useAuthStore.getState().setSession({ username: 'synthetic' }, 'synthetic-account-proof')
    let failure
    try {
      await api.get(url, { adapter: async (config) => {
        throw { config, response: { status: 401, data: { detail: 'Not authorized' } } }
      } })
    } catch (error) { failure = error }
    expect(failure.status).toBe(401)
    expect(failure.config).toBeUndefined()
    expect(useAuthStore.getState().isAuthenticated).toBe(url.startsWith('/guest/'))
  })
})
