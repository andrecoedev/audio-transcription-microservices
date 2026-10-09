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

  async signInWithEmail(email, password) {
    const authContext = await getAuthContext()
    await authContext.ready
    try {
      const result = await authContext.sdk.signInWithEmailAndPassword(authContext.auth, email, password)
      return emailResult(result.user)
    } catch (error) { throw safeAuthError(error) }
  },

  async createWithEmail(email, password) {
    const authContext = await getAuthContext()
    await authContext.ready
    try {
      const passwordStatus = await authContext.sdk.validatePassword(authContext.auth, password)
      if (!passwordStatus.isValid) throw weakPasswordError()
      const result = await authContext.sdk.createUserWithEmailAndPassword(authContext.auth, email, password)
      if (!result.user.emailVerified) await authContext.sdk.sendEmailVerification(result.user)
      return emailResult(result.user)
    } catch (error) { throw error?.code === 'auth/weak-password' ? error : safeAuthError(error) }
  },

  async validatePassword(password) {
    const authContext = await getAuthContext()
    await authContext.ready
    try { return await authContext.sdk.validatePassword(authContext.auth, password) }
    catch (error) { throw safeAuthError(error) }
  },

  async getEmailVerificationState() {
    const authContext = await getAuthContextOrNull()
    if (!authContext) return null
    await authContext.ready
    const user = authContext.auth.currentUser
    return user ? emailResult(user) : null
  },

  async resendVerification() {
    const authContext = await getAuthContext()
    await authContext.ready
    const user = requireCurrentUser(authContext.auth)
    try { await authContext.sdk.sendEmailVerification(user) } catch (error) { throw safeAuthError(error) }
  },

  async refreshVerification() {
    const authContext = await getAuthContext()
    await authContext.ready
    const user = requireCurrentUser(authContext.auth)
    try {
      await authContext.sdk.reload(user)
      const currentUser = authContext.auth.currentUser
      if (!currentUser || currentUser.uid !== user.uid) throw accountChangedError()
      return emailResult(currentUser, true)
    } catch (error) { throw error?.code === 'auth/account-changed' ? error : safeAuthError(error) }
  },

  async resetPassword(email) {
    const authContext = await getAuthContext()
    await authContext.ready
    try {
      await authContext.sdk.sendPasswordResetEmail(authContext.auth, email)
    } catch (error) {
      if (error?.code !== 'auth/user-not-found') throw safeAuthError(error)
    }
  },

  async linkPassword(email, password) {
    const authContext = await getAuthContext()
    await authContext.ready
    const user = requireCurrentUser(authContext.auth)
    try {
      if (!user.email || email !== user.email) {
        const error = new Error('O e-mail deve corresponder ao da conta atual.')
        error.code = 'auth/email-mismatch'
        throw error
      }
      const credential = authContext.sdk.EmailAuthProvider.credential(email, password)
      const result = await authContext.sdk.linkWithCredential(user, credential)
      if (result.user.uid !== user.uid) throw accountChangedError()
      if (!result.user.emailVerified) await authContext.sdk.sendEmailVerification(result.user)
      return emailResult(result.user)
    } catch (error) {
      if (error?.code === 'auth/email-mismatch' || error?.code === 'auth/account-changed') throw error
      throw safeAuthError(error)
    }
  },

  async reauthenticatePassword(password) {
    const authContext = await getAuthContext()
    await authContext.ready
    const user = requireCurrentUser(authContext.auth)
    try {
      if (!user.email) {
        const error = new Error('Esta conta não tem um e-mail para reautenticar.')
        error.code = 'auth/email-required'
        throw error
      }
      const credential = authContext.sdk.EmailAuthProvider.credential(user.email, password)
      await authContext.sdk.reauthenticateWithCredential(user, credential)
    } catch (error) {
      if (error?.code === 'auth/email-required') throw error
      throw safeAuthError(error)
    }
  },

  async linkGoogle() {
    const authContext = await getAuthContext()
    await authContext.ready
    const user = requireCurrentUser(authContext.auth)
    const provider = new authContext.sdk.GoogleAuthProvider()
    provider.setCustomParameters({ prompt: 'select_account' })
    try {
      const result = await authContext.sdk.linkWithPopup(user, provider)
      return { verified: Boolean(result.user.emailVerified), methods: providerIds(result.user) }
    } catch (error) { throw safeAuthError(error) }
  },

  async getAuthMethods() {
    const authContext = await getAuthContextOrNull()
    if (!authContext) return []
    await authContext.ready
    return providerIds(authContext.auth.currentUser)
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

async function emailResult(user, forceRefresh = false) {
  const verified = Boolean(user.emailVerified)
  try { return { verified, token: verified ? await user.getIdToken(forceRefresh) : null } }
  catch (error) { throw safeAuthError(error) }
}

function providerIds(user) {
  return Array.isArray(user?.providerData)
    ? [...new Set(user.providerData.map((provider) => provider?.providerId).filter((id) => typeof id === 'string'))]
    : []
}

function requireCurrentUser(auth) {
  if (!auth.currentUser) {
    const error = new Error('Entre na sua conta para continuar.')
    error.code = 'auth/no-current-user'
    throw error
  }
  return auth.currentUser
}

function accountChangedError() {
  const error = new Error('A conta mudou. Entre novamente para continuar.')
  error.code = 'auth/account-changed'
  return error
}

function weakPasswordError() {
  const error = new Error('A senha não atende aos requisitos de segurança configurados.')
  error.code = 'auth/weak-password'
  return error
}

function safeAuthError(error) {
  const messages = {
    'auth/email-already-in-use': 'Este e-mail já está em uso.',
    'auth/invalid-credential': 'E-mail ou senha inválidos.',
    'auth/invalid-email': 'Informe um e-mail válido.',
    'auth/weak-password': 'Escolha uma senha mais forte.',
    'auth/too-many-requests': 'Muitas tentativas. Aguarde e tente novamente.',
    'auth/network-request-failed': 'Não foi possível conectar. Verifique sua conexão e tente novamente.',
    'auth/provider-already-linked': 'Este método de acesso já está conectado.',
    'auth/credential-already-in-use': 'Este método de acesso já pertence a outra conta.',
    'auth/requires-recent-login': 'Entre novamente para confirmar esta alteração.',
    'auth/email-mismatch': 'O e-mail deve corresponder ao da conta atual.',
    'auth/email-required': 'Esta conta não tem um e-mail para reautenticar.',
  }
  const failure = new Error(messages[error?.code] || 'Não foi possível concluir a operação. Tente novamente.')
  failure.code = typeof error?.code === 'string' ? error.code : 'auth/operation-failed'
  return failure
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
      auth.languageCode = 'pt-BR'
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
