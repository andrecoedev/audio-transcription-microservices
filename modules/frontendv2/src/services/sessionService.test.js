import { beforeEach, describe, expect, it, vi } from 'vitest'
import { restoreSession, endSession } from './sessionService'
import { authService } from './authService'
import { firebaseAuth } from './firebaseAuth'
import { useAuthStore } from '../stores/authStore'

vi.mock('./authService', () => ({ authService: { me: vi.fn() } }))
vi.mock('./firebaseAuth', () => ({ firebaseAuth: { getToken: vi.fn(), signOut: vi.fn() } }))
const user = { id: 7, username: 'synthetic-user', display_name: 'Nome público', registration_source: 'public' }
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); sessionStorage.clear()
  useAuthStore.getState().logout()
})
describe('Firebase session boundaries', () => {
  it('does not log out a new account when an old restoration receives 401', async () => {
    useAuthStore.getState().setFirebaseSession(user)
    firebaseAuth.getToken.mockResolvedValue('synthetic-proof')
    authService.me.mockImplementation(async () => {
      useAuthStore.getState().setFirebaseSession({ ...user, id: 8 })
      throw { status: 401 }
    })
    await restoreSession()
    expect(useAuthStore.getState().user.id).toBe(8)
    expect(firebaseAuth.signOut).not.toHaveBeenCalled()
  })
  it('preserves renewable session metadata on an API outage without granting a new identity', async () => {
    useAuthStore.getState().setFirebaseSession(user)
    firebaseAuth.getToken.mockResolvedValue('synthetic-proof')
    authService.me.mockRejectedValue({ status: 503 })
    await expect(restoreSession()).rejects.toMatchObject({ status: 503 })
    expect(useAuthStore.getState().user.id).toBe(7)
    expect(firebaseAuth.signOut).not.toHaveBeenCalled()
  })
  it('cannot restore an in-flight session after explicit logout', async () => {
    useAuthStore.getState().setFirebaseSession(user)
    firebaseAuth.getToken.mockResolvedValue('synthetic-proof')
    authService.me.mockImplementation(async () => {
      useAuthStore.getState().logout()
      return { authenticated: true, user }
    })
    await restoreSession()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
  it('restores a verified internal user without copying Firebase credentials to app storage', async () => {
    useAuthStore.getState().setFirebaseSession(user)
    firebaseAuth.getToken.mockResolvedValue('synthetic-runtime-proof')
    authService.me.mockResolvedValue({ authenticated: true, user })
    await restoreSession()
    expect(useAuthStore.getState().user.id).toBe(7)
    expect(useAuthStore.getState().user.name).toBe('Nome público')
    expect(useAuthStore.getState().token).toBeNull()
    expect(JSON.stringify(localStorage)).not.toContain('synthetic-runtime-proof')
    expect(localStorage.getItem('token')).toBeNull()
  })
  it('does not accept an expired SDK session or fall back to a stale local token', async () => {
    useAuthStore.getState().setFirebaseSession(user)
    localStorage.setItem('token', 'stale-local-proof')
    firebaseAuth.getToken.mockResolvedValue(null)
    await restoreSession()
    expect(authService.me).not.toHaveBeenCalled()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
  it('logs out of Firebase while preserving tab-scoped Guest context', async () => {
    useAuthStore.getState().setFirebaseSession(user)
    sessionStorage.setItem('usagi-guest-session', 'synthetic-guest-proof')
    await endSession()
    expect(firebaseAuth.signOut).toHaveBeenCalledOnce()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(sessionStorage.getItem('usagi-guest-session')).toBe('synthetic-guest-proof')
  })
  it('clears domain access and reports an external logout failure', async () => {
    useAuthStore.getState().setFirebaseSession(user)
    firebaseAuth.signOut.mockRejectedValue(new Error('synthetic failure'))
    await expect(endSession()).rejects.toThrow()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
  it('retains the existing local session contract', async () => {
    useAuthStore.getState().setSession(user, 'synthetic-local-proof')
    authService.me.mockResolvedValue({ authenticated: true, user })
    await restoreSession()
    expect(firebaseAuth.getToken).not.toHaveBeenCalled()
    expect(useAuthStore.getState().token).toBe('synthetic-local-proof')
  })
})
