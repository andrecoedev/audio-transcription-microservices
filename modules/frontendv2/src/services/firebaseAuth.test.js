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
  signInWithEmailAndPassword: vi.fn(),
  createUserWithEmailAndPassword: vi.fn(),
  sendEmailVerification: vi.fn().mockResolvedValue(undefined),
  validatePassword: vi.fn().mockResolvedValue({ isValid: true }),
  sendPasswordResetEmail: vi.fn().mockResolvedValue(undefined),
  reload: vi.fn().mockResolvedValue(undefined),
  linkWithCredential: vi.fn(),
  reauthenticateWithCredential: vi.fn().mockResolvedValue(undefined),
  linkWithPopup: vi.fn(),
  EmailAuthProvider: { credential: vi.fn((email, password) => ({ email, password })) },
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
  signInWithEmailAndPassword: sdk.signInWithEmailAndPassword,
  createUserWithEmailAndPassword: sdk.createUserWithEmailAndPassword,
  sendEmailVerification: sdk.sendEmailVerification,
  validatePassword: sdk.validatePassword,
  sendPasswordResetEmail: sdk.sendPasswordResetEmail,
  reload: sdk.reload,
  linkWithCredential: sdk.linkWithCredential,
  reauthenticateWithCredential: sdk.reauthenticateWithCredential,
  linkWithPopup: sdk.linkWithPopup,
  EmailAuthProvider: sdk.EmailAuthProvider,
  signOut: sdk.signOut,
  onIdTokenChanged: sdk.onIdTokenChanged,
}))

const configuredEnv = {
  VITE_FIREBASE_API_KEY: 'public-api-key',
  VITE_FIREBASE_AUTH_DOMAIN: 'example.firebaseapp.com',
  VITE_FIREBASE_PROJECT_ID: 'example-project',
  VITE_FIREBASE_APP_ID: '1:123456789:web:0000000000000000000000',
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
  sdk.auth.languageCode = undefined
  sdk.auth.authStateReady.mockClear().mockResolvedValue(undefined)
  sdk.initializeApp.mockClear()
  sdk.getApps.mockClear()
  sdk.getAuth.mockClear()
  sdk.setPersistence.mockClear().mockResolvedValue(undefined)
  sdk.GoogleAuthProvider.mockClear()
  sdk.signInWithPopup.mockReset()
  sdk.signInWithEmailAndPassword.mockReset()
  sdk.createUserWithEmailAndPassword.mockReset()
  sdk.sendEmailVerification.mockClear().mockResolvedValue(undefined)
  sdk.validatePassword.mockClear().mockResolvedValue({ isValid: true })
  sdk.sendPasswordResetEmail.mockClear().mockResolvedValue(undefined)
  sdk.reload.mockClear().mockResolvedValue(undefined)
  sdk.linkWithCredential.mockReset()
  sdk.reauthenticateWithCredential.mockClear().mockResolvedValue(undefined)
  sdk.linkWithPopup.mockReset()
  sdk.EmailAuthProvider.credential.mockClear()
  sdk.signOut.mockClear().mockResolvedValue(undefined)
  sdk.onIdTokenChanged.mockClear()
  sdk.unsubscribe.mockClear()
  sdk.observer = null
})

afterEach(() => vi.unstubAllEnvs())

describe('firebaseAuth', () => {
  it.each([
    ['VITE_FIREBASE_PROJECT_ID', 'your-firebase-project-id'],
    ['VITE_FIREBASE_PROJECT_ID', 'INVALID_PROJECT'],
    ['VITE_FIREBASE_AUTH_DOMAIN', 'https://example.firebaseapp.com'],
    ['VITE_FIREBASE_AUTH_DOMAIN', 'example.firebaseapp.com/path'],
    ['VITE_FIREBASE_APP_ID', 'public-app-id'],
    ['VITE_FIREBASE_API_KEY', 'invalid key with spaces'],
  ])('does not initialize Google for invalid public config %s', async (key, value) => {
    vi.stubEnv(key, value)
    const service = await loadService()
    expect(service.isConfigured()).toBe(false)
    expect(service.projectId()).toBeNull()
    await expect(service.signInWithGoogle()).rejects.toMatchObject({ code: 'auth/not-configured' })
    expect(sdk.initializeApp).not.toHaveBeenCalled()
  })
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
      appId: '1:123456789:web:0000000000000000000000',
    }, 'usagi-auth')
    expect(sdk.setPersistence).toHaveBeenCalledWith(sdk.auth, sdk.browserLocalPersistence)
    expect(sdk.auth.languageCode).toBe('pt-BR')
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

  it('creates an unverified email account, sends verification, and withholds its token', async () => {
    const user = { uid: 'uid-a', emailVerified: false, getIdToken: vi.fn() }
    sdk.createUserWithEmailAndPassword.mockResolvedValue({ user })
    const service = await loadService()

    await expect(service.createWithEmail('a@example.test', 'private-password'))
      .resolves.toEqual({ verified: false, token: null })
    expect(sdk.createUserWithEmailAndPassword).toHaveBeenCalledWith(sdk.auth, 'a@example.test', 'private-password')
    expect(sdk.validatePassword).toHaveBeenCalledWith(sdk.auth, 'private-password')
    expect(sdk.sendEmailVerification).toHaveBeenCalledWith(user)
    expect(user.getIdToken).not.toHaveBeenCalled()
  })

  it('uses Firebase password policy before creating an account', async () => {
    sdk.validatePassword.mockResolvedValue({ isValid: false, meetsMinPasswordLength: false })
    const service = await loadService()

    await expect(service.createWithEmail('a@example.test', 'private-password'))
      .rejects.toMatchObject({ code: 'auth/weak-password', message: 'A senha não atende aos requisitos de segurança configurados.' })
    expect(sdk.createUserWithEmailAndPassword).not.toHaveBeenCalled()
  })

  it('validates passwords with Firebase and reads current email verification without storing credentials', async () => {
    sdk.validatePassword.mockResolvedValue({ isValid: false, meetsMinPasswordLength: false })
    const service = await loadService()
    await expect(service.validatePassword('private-password')).resolves.toEqual({ isValid: false, meetsMinPasswordLength: false })
    await expect(service.getEmailVerificationState()).resolves.toBeNull()

    const user = { emailVerified: false, getIdToken: vi.fn() }
    sdk.auth.currentUser = user
    await expect(service.getEmailVerificationState()).resolves.toEqual({ verified: false, token: null })
    expect(user.getIdToken).not.toHaveBeenCalled()
  })

  it('signs in email users and returns an ID token only when verified', async () => {
    const user = { emailVerified: true, getIdToken: vi.fn().mockResolvedValue('verified-id-token') }
    sdk.signInWithEmailAndPassword.mockResolvedValue({ user })
    const service = await loadService()

    await expect(service.signInWithEmail('a@example.test', 'private-password'))
      .resolves.toEqual({ verified: true, token: 'verified-id-token' })
    expect(user.getIdToken).toHaveBeenCalledOnce()
  })

  it('refreshes verification from the same current Firebase user and forces a new token', async () => {
    const user = { uid: 'uid-a', emailVerified: false, getIdToken: vi.fn().mockResolvedValue('refreshed-id-token') }
    sdk.auth.currentUser = user
    sdk.reload.mockImplementation(async () => { user.emailVerified = true })
    const service = await loadService()

    await expect(service.refreshVerification()).resolves.toEqual({ verified: true, token: 'refreshed-id-token' })
    expect(sdk.reload).toHaveBeenCalledWith(user)
    expect(user.getIdToken).toHaveBeenCalledWith(true)
  })

  it('resends verification and sends password reset without exposing unknown accounts', async () => {
    const user = { uid: 'uid-a', emailVerified: false }
    sdk.auth.currentUser = user
    const service = await loadService()
    await service.resendVerification()
    expect(sdk.sendEmailVerification).toHaveBeenCalledWith(user)
    sdk.sendPasswordResetEmail.mockRejectedValueOnce(Object.assign(new Error('private SDK detail'), { code: 'auth/user-not-found' }))
    await expect(service.resetPassword('missing@example.test')).resolves.toBeUndefined()
  })

  it('links email/password and Google credentials to the current account only', async () => {
    const user = { uid: 'uid-a', email: 'a@example.test', emailVerified: true, providerData: [{ providerId: 'password' }], getIdToken: vi.fn().mockResolvedValue('linked-id-token') }
    sdk.auth.currentUser = user
    sdk.linkWithCredential.mockResolvedValue({ user })
    sdk.linkWithPopup.mockResolvedValue({ user: { ...user, providerData: [...user.providerData, { providerId: 'google.com' }] } })
    const service = await loadService()

    await expect(service.linkPassword('a@example.test', 'private-password'))
      .resolves.toEqual({ verified: true, token: 'linked-id-token' })
    const credential = { email: 'a@example.test', password: 'private-password' }
    expect(sdk.EmailAuthProvider.credential).toHaveBeenCalledWith('a@example.test', 'private-password')
    expect(sdk.linkWithCredential).toHaveBeenCalledWith(user, credential)
    await expect(service.linkGoogle()).resolves.toEqual({ verified: true, methods: ['password', 'google.com'] })
    expect(sdk.linkWithPopup).toHaveBeenCalledWith(user, expect.any(sdk.GoogleAuthProvider))
    expect(sdk.signInWithPopup).not.toHaveBeenCalled()
  })

  it('reauthenticates with the current user email and refuses a different password-link email', async () => {
    const user = { uid: 'uid-a', email: 'current@example.test' }
    sdk.auth.currentUser = user
    const service = await loadService()

    await service.reauthenticatePassword('private-password')
    const credential = { email: 'current@example.test', password: 'private-password' }
    expect(sdk.EmailAuthProvider.credential).toHaveBeenCalledWith('current@example.test', 'private-password')
    expect(sdk.reauthenticateWithCredential).toHaveBeenCalledWith(user, credential)
    await expect(service.linkPassword('other@example.test', 'private-password'))
      .rejects.toMatchObject({ code: 'auth/email-mismatch' })
    expect(sdk.linkWithCredential).not.toHaveBeenCalled()
  })

  it('returns only provider IDs and sanitizes SDK errors', async () => {
    sdk.auth.currentUser = { providerData: [{ providerId: 'password' }, { providerId: 'google.com' }, { providerId: 'password' }] }
    const service = await loadService()
    await expect(service.getAuthMethods()).resolves.toEqual(['password', 'google.com'])
    sdk.signInWithEmailAndPassword.mockRejectedValueOnce(Object.assign(new Error('private raw details'), { code: 'auth/invalid-credential' }))
    await expect(service.signInWithEmail('a@example.test', 'private-password'))
      .rejects.toMatchObject({ message: 'E-mail ou senha inválidos.', code: 'auth/invalid-credential' })
  })
})
