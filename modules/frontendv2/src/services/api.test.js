import { beforeEach, describe, expect, it, vi } from 'vitest'
import api from './api'
import { useAuthStore } from '../stores/authStore'
import { firebaseAuth } from './firebaseAuth'
vi.mock('./firebaseAuth', () => ({ firebaseAuth: { getTokenContext: vi.fn(), signOut: vi.fn() } }))

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  useAuthStore.setState({ token: null, user: null, isAuthenticated: false, authProvider: 'local' })
})

describe('HTTP credential boundaries', () => {
  it('clears an SDK-revoked identity before sending a request', async () => {
    useAuthStore.getState().setFirebaseSession({ id: 7 })
    firebaseAuth.getTokenContext.mockRejectedValue({ code: 'auth/user-disabled' })
    const adapter = vi.fn()
    await expect(api.get('/transcriptions', { adapter })).rejects.toThrow('Entre novamente')
    expect(adapter).not.toHaveBeenCalled()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(firebaseAuth.signOut).toHaveBeenCalledOnce()
  })
  it('renews a rejected Firebase token once without logging out a renewable session', async () => {
    useAuthStore.getState().setFirebaseSession({ id: 7 })
    firebaseAuth.getTokenContext.mockResolvedValueOnce({ token: 'synthetic-old-proof', uid: 'synthetic-uid' }).mockResolvedValue({ token: 'synthetic-new-proof', uid: 'synthetic-uid' })
    let attempts = 0
    const result = await api.get('/transcriptions', { adapter: async (config) => {
      attempts += 1
      if (attempts === 1) throw { config, response: { status: 401, data: {} } }
      expect(config.headers.Authorization).toBe('Bearer synthetic-new-proof')
      return { data: { ok: true }, status: 200, headers: {}, config }
    } })
    expect(result.data.ok).toBe(true)
    expect(firebaseAuth.getTokenContext).toHaveBeenCalledWith(true)
    expect(firebaseAuth.signOut).not.toHaveBeenCalled()
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(localStorage.getItem('token')).toBeNull()
  })
  it('gets refreshed SDK tokens at request time without persisting them', async () => {
    useAuthStore.getState().setFirebaseSession({ id: 7 })
    firebaseAuth.getTokenContext.mockResolvedValue({ token: 'synthetic-refreshed-proof', uid: 'synthetic-uid' })
    await api.get('/transcriptions', { adapter: async (config) => {
      expect(config.headers.Authorization).toBe('Bearer synthetic-refreshed-proof')
      return { data: {}, status: 200, headers: {}, config }
    } })
    expect(localStorage.getItem('token')).toBeNull()
  })
  it('stops after one retry and respects a server rejection of a revoked identity', async () => {
    useAuthStore.getState().setFirebaseSession({ id: 7 })
    firebaseAuth.getTokenContext.mockResolvedValue({ token: 'synthetic-proof', uid: 'synthetic-uid' })
    let attempts = 0
    await expect(api.get('/transcriptions', { adapter: async config => {
      attempts += 1
      throw { config, response: { status: 401, data: {} } }
    } })).rejects.toMatchObject({ status: 401 })
    expect(attempts).toBe(2)
    expect(firebaseAuth.signOut).toHaveBeenCalledOnce()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
  it('does not replay an old request under a different Firebase identity', async () => {
    useAuthStore.getState().setFirebaseSession({ id: 7 })
    firebaseAuth.getTokenContext.mockResolvedValueOnce({ token: 'synthetic-proof', uid: 'first' })
      .mockResolvedValue({ token: 'synthetic-other-proof', uid: 'second' })
    const adapter = vi.fn(async config => { throw { config, response: { status: 401, data: {} } } })
    await expect(api.get('/transcriptions', { adapter })).rejects.toThrow('A conta mudou')
    expect(adapter).toHaveBeenCalledOnce()
    expect(firebaseAuth.signOut).not.toHaveBeenCalled()
  })
  it('keeps the SDK session on a temporary refresh network failure', async () => {
    useAuthStore.getState().setFirebaseSession({ id: 7 })
    firebaseAuth.getTokenContext.mockResolvedValueOnce({ token: 'synthetic-proof', uid: 'first' })
      .mockRejectedValue({ code: 'auth/network-request-failed' })
    await expect(api.get('/transcriptions', { adapter: async config => {
      throw { config, response: { status: 401, data: {} } }
    } })).rejects.toThrow('Verifique sua conexão')
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(firebaseAuth.signOut).not.toHaveBeenCalled()
  })
  it('never replaces explicit Guest proof with a Firebase token', async () => {
    useAuthStore.getState().setFirebaseSession({ id: 7 })
    await api.get('/guest/session', { headers: { Authorization: 'Bearer synthetic-guest-proof' }, adapter: async (config) => {
      expect(config.headers.Authorization).toBe('Bearer synthetic-guest-proof')
      return { data: {}, status: 200, headers: {}, config }
    } })
    expect(firebaseAuth.getTokenContext).not.toHaveBeenCalled()
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
