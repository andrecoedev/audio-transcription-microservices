const APP_NAME = 'usagi-auth'

function readFirebaseConfig() {
  const env = import.meta.env ?? {}
  const config = {
    apiKey: env.VITE_FIREBASE_API_KEY,
    authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: env.VITE_FIREBASE_PROJECT_ID,
    appId: env.VITE_FIREBASE_APP_ID,
  }

  return Object.values(config).every((value) => typeof value === 'string' && value.trim())
    ? Object.fromEntries(Object.entries(config).map(([key, value]) => [key, value.trim()]))
    : null
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

  async getToken() {
    const authContext = await getAuthContextOrNull()
    if (!authContext) return null

    await authContext.ready
    return authContext.auth.currentUser?.getIdToken() ?? null
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
    return authContext.sdk.onIdTokenChanged(authContext.auth, (user) => callback(Boolean(user)))
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
