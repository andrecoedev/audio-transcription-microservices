import { beforeEach, describe, expect, it, vi } from 'vitest'
import api from './api'
import { useAuthStore } from '../stores/authStore'
import { firebaseAuth } from './firebaseAuth'
vi.mock('./firebaseAuth', () => ({ firebaseAuth: { getToken: vi.fn(), signOut: vi.fn() } }))

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  useAuthStore.setState({ token: null, user: null, isAuthenticated: false, authProvider: 'local' })
})

describe('HTTP credential boundaries', () => {
  it('gets refreshed SDK tokens at request time without persisting them', async () => {
    useAuthStore.getState().setFirebaseSession({ id: 7 })
    firebaseAuth.getToken.mockResolvedValue('synthetic-refreshed-proof')
    await api.get('/transcriptions', { adapter: async (config) => {
      expect(config.headers.Authorization).toBe('Bearer synthetic-refreshed-proof')
      return { data: {}, status: 200, headers: {}, config }
    } })
    expect(localStorage.getItem('token')).toBeNull()
  })
  it('never replaces explicit Guest proof with a Firebase token', async () => {
    useAuthStore.getState().setFirebaseSession({ id: 7 })
    await api.get('/guest/session', { headers: { Authorization: 'Bearer synthetic-guest-proof' }, adapter: async (config) => {
      expect(config.headers.Authorization).toBe('Bearer synthetic-guest-proof')
      return { data: {}, status: 200, headers: {}, config }
    } })
    expect(firebaseAuth.getToken).not.toHaveBeenCalled()
  })
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
