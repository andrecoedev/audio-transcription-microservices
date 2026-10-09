const APP_NAME = 'usagi-auth'

function readFirebaseConfig() {
  const env = import.meta.env ?? {}
  const config = {
    apiKey: env.VITE_FIREBASE_API_KEY,
    authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: env.VITE_FIREBASE_PROJECT_ID,
    appId: env.VITE_FIREBASE_APP_ID,
  }

  if (!Object.values(config).every((value) => typeof value === 'string' && value.trim())) return null
  const normalized = Object.fromEntries(Object.entries(config).map(([key, value]) => [key, value.trim()]))
  if (Object.values(normalized).some((value) => /^your-|^replace[-_]|\$\{/i.test(value))) return null
  if (/\s/.test(normalized.apiKey)
      || !/^[a-z0-9][a-z0-9-]{4,127}$/.test(normalized.projectId)
      || !/^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$/i.test(normalized.authDomain)
      || !/^1:[0-9]+:web:[a-f0-9]+$/i.test(normalized.appId)) return null
  return normalized
}

function notConfiguredError() {
  const error = new Error('Firebase authentication is not configured.')
  error.code = 'auth/not-configured'
  return error
}

export const firebaseAuth = {
  isConfigured() {
    return readFirebaseConfig() !== null
  },

  projectId() {
    return readFirebaseConfig()?.projectId ?? null
  },

  async signInWithGoogle() {
    const authContext = await getAuthContext()
    await authContext.ready
    const provider = new authContext.sdk.GoogleAuthProvider()
    provider.setCustomParameters({ prompt: 'select_account' })
    const result = await authContext.sdk.signInWithPopup(authContext.auth, provider)
    return result.user.getIdToken()
  },

  async getToken(forceRefresh = false) {
    const authContext = await getAuthContextOrNull()
    if (!authContext) return null

    await authContext.ready
    return authContext.auth.currentUser?.getIdToken(forceRefresh) ?? null
  },

  async getTokenContext(forceRefresh = false) {
    const authContext = await getAuthContextOrNull()
    if (!authContext) return null
    await authContext.ready
    const user = authContext.auth.currentUser
    if (!user) return null
    const token = await user.getIdToken(forceRefresh)
    if (authContext.auth.currentUser?.uid !== user.uid) {
      const error = new Error('A conta mudou. Tente novamente.')
      error.code = 'auth/account-changed'
      throw error
    }
    return { token, uid: user.uid }
  },

  async signOut() {
    const authContext = await getAuthContextOrNull()
    if (!authContext) return

    await authContext.ready
    await authContext.sdk.signOut(authContext.auth)
  },

  async observe(callback) {
    const authContext = await getAuthContextOrNull()
    if (!authContext) return () => {}

    await authContext.ready
    return authContext.sdk.onIdTokenChanged(authContext.auth, (user) => callback(Boolean(user), user?.uid ?? null))
  },
}

let authContextPromise

async function getAuthContextOrNull() {
  if (!readFirebaseConfig()) return null
  return getAuthContext()
}

function getAuthContext() {
  const config = readFirebaseConfig()
  if (!config) return Promise.reject(notConfiguredError())
  if (authContextPromise) return authContextPromise

  authContextPromise = Promise.all([import('firebase/app'), import('firebase/auth')])
    .then(async ([appSdk, authSdk]) => {
      const existingApp = appSdk.getApps().find((app) => app.name === APP_NAME)
      const app = existingApp ?? appSdk.initializeApp(config, APP_NAME)
      const auth = authSdk.getAuth(app)
      await authSdk.setPersistence(auth, authSdk.browserLocalPersistence)
      await auth.authStateReady()
      return { app, auth, sdk: authSdk, ready: Promise.resolve() }
    })
    .catch((error) => {
      authContextPromise = undefined
      throw error
    })

  return authContextPromise
}
