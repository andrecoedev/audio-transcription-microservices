import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const sdk = vi.hoisted(() => ({
  apps: [],
  auth: { currentUser: null, authStateReady: vi.fn().mockResolvedValue(undefined) },
  initializeApp: vi.fn((config, name) => {
    const app = { config, name }
    sdk.apps.push(app)
    return app
  }),
  getApps: vi.fn(() => sdk.apps),
  getAuth: vi.fn(() => sdk.auth),
  setPersistence: vi.fn().mockResolvedValue(undefined),
  browserLocalPersistence: { type: 'LOCAL' },
  GoogleAuthProvider: vi.fn(function GoogleAuthProvider() {
    this.setCustomParameters = vi.fn()
  }),
  signInWithPopup: vi.fn(),
  signOut: vi.fn().mockResolvedValue(undefined),
  onIdTokenChanged: vi.fn((_auth, callback) => {
    sdk.observer = callback
    return sdk.unsubscribe
  }),
  unsubscribe: vi.fn(),
  observer: null,
}))

vi.mock('firebase/app', () => ({
  getApps: sdk.getApps,
  initializeApp: sdk.initializeApp,
}))

vi.mock('firebase/auth', () => ({
  getAuth: sdk.getAuth,
  setPersistence: sdk.setPersistence,
  browserLocalPersistence: sdk.browserLocalPersistence,
  GoogleAuthProvider: sdk.GoogleAuthProvider,
  signInWithPopup: sdk.signInWithPopup,
  signOut: sdk.signOut,
  onIdTokenChanged: sdk.onIdTokenChanged,
}))

const configuredEnv = {
  VITE_FIREBASE_API_KEY: 'public-api-key',
  VITE_FIREBASE_AUTH_DOMAIN: 'example.firebaseapp.com',
  VITE_FIREBASE_PROJECT_ID: 'example-project',
  VITE_FIREBASE_APP_ID: 'public-app-id',
}

async function loadService() {
  vi.resetModules()
  return (await import('./firebaseAuth')).firebaseAuth
}

beforeEach(() => {
  vi.unstubAllEnvs()
  for (const [key, value] of Object.entries(configuredEnv)) vi.stubEnv(key, value)
  sdk.apps.length = 0
  sdk.auth.currentUser = null
  sdk.auth.authStateReady.mockClear().mockResolvedValue(undefined)
  sdk.initializeApp.mockClear()
  sdk.getApps.mockClear()
  sdk.getAuth.mockClear()
  sdk.setPersistence.mockClear().mockResolvedValue(undefined)
  sdk.GoogleAuthProvider.mockClear()
  sdk.signInWithPopup.mockReset()
  sdk.signOut.mockClear().mockResolvedValue(undefined)
  sdk.onIdTokenChanged.mockClear()
  sdk.unsubscribe.mockClear()
  sdk.observer = null
})

afterEach(() => vi.unstubAllEnvs())

describe('firebaseAuth', () => {
  it('passes force refresh to the SDK and guards against switching users during refresh', async () => {
    const getIdToken = vi.fn().mockResolvedValue('synthetic-proof')
    sdk.auth.currentUser = { uid: 'first', getIdToken }
    const service = await loadService()
    await expect(service.getTokenContext(true)).resolves.toEqual({ token: 'synthetic-proof', uid: 'first' })
    expect(getIdToken).toHaveBeenCalledWith(true)
    getIdToken.mockImplementation(async () => {
      sdk.auth.currentUser = { uid: 'second' }
      return 'synthetic-proof'
    })
    await expect(service.getTokenContext(true)).rejects.toMatchObject({ code: 'auth/account-changed' })
  })
  it('does not initialize Firebase when any required public setting is missing', async () => {
    vi.stubEnv('VITE_FIREBASE_APP_ID', '')
    const service = await loadService()

    expect(service.isConfigured()).toBe(false)
    expect(service.projectId()).toBeNull()
    await expect(service.signInWithGoogle()).rejects.toMatchObject({ code: 'auth/not-configured' })
    await expect(service.getToken()).resolves.toBeNull()
    await expect(service.signOut()).resolves.toBeUndefined()
    await expect(service.observe(vi.fn())).resolves.toEqual(expect.any(Function))
    expect(sdk.initializeApp).not.toHaveBeenCalled()
    expect(sdk.getAuth).not.toHaveBeenCalled()
  })

  it('uses local persistence and returns the Firebase ID token from Google popup sign-in', async () => {
    const getIdToken = vi.fn().mockResolvedValue('firebase-id-token')
    sdk.signInWithPopup.mockResolvedValue({
      user: { getIdToken },
      credential: { accessToken: 'google-oauth-access-token' },
    })
    const service = await loadService()

    await expect(service.signInWithGoogle()).resolves.toBe('firebase-id-token')
    expect(sdk.initializeApp).toHaveBeenCalledWith({
      apiKey: 'public-api-key',
      authDomain: 'example.firebaseapp.com',
      projectId: 'example-project',
      appId: 'public-app-id',
    }, 'usagi-auth')
    expect(sdk.setPersistence).toHaveBeenCalledWith(sdk.auth, sdk.browserLocalPersistence)
    expect(sdk.auth.authStateReady).toHaveBeenCalledOnce()
    const provider = sdk.signInWithPopup.mock.calls[0][1]
    expect(provider.setCustomParameters).toHaveBeenCalledWith({ prompt: 'select_account' })
    expect(getIdToken).toHaveBeenCalledOnce()
  })

  it('waits for auth restoration before reading a token and returns null for signed-out users', async () => {
    const getIdToken = vi.fn().mockResolvedValue('restored-id-token')
    sdk.auth.currentUser = { getIdToken }
    const service = await loadService()

    await expect(service.getToken()).resolves.toBe('restored-id-token')
    expect(sdk.auth.authStateReady).toHaveBeenCalledOnce()
    sdk.auth.currentUser = null
    await expect(service.getToken()).resolves.toBeNull()
  })

  it('signs out through Firebase after auth restoration', async () => {
    const service = await loadService()

    await service.signOut()
    expect(sdk.auth.authStateReady).toHaveBeenCalledOnce()
    expect(sdk.signOut).toHaveBeenCalledWith(sdk.auth)
  })

  it('observes token changes as signed-in booleans and returns the SDK unsubscribe function', async () => {
    const service = await loadService()
    const callback = vi.fn()

    const unsubscribe = await service.observe(callback)
    expect(sdk.onIdTokenChanged).toHaveBeenCalledWith(sdk.auth, expect.any(Function))
    sdk.observer({ uid: 'user-id' })
    sdk.observer(null)
    expect(callback.mock.calls).toEqual([[true, 'user-id'], [false, null]])
    expect(unsubscribe).toBe(sdk.unsubscribe)
  })

  it('exposes only the safe configured project ID', async () => {
    const service = await loadService()

    expect(service.isConfigured()).toBe(true)
    expect(service.projectId()).toBe('example-project')
    expect(sdk.initializeApp).not.toHaveBeenCalled()
  })
})
