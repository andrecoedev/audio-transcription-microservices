// Synthetic identity boundary for the isolated journey only; no real SDK/network.
const key = 'beta-e2e-synthetic-identity'
const read = () => JSON.parse(localStorage.getItem(key) || 'null')
const signed = (name) => {
  if (!['member', 'other', 'google'].includes(name)) throw new Error('Unknown synthetic persona')
  localStorage.setItem(key, JSON.stringify({ uid: name, token: `beta-e2e-${name}` }))
  return { verified: true, token: `beta-e2e-${name}` }
}
export const firebaseAuth = {
  isConfigured: () => true,
  projectId: () => 'usagi-beta-e2e',
  validatePassword: async (value) => ({ isValid: value.length >= 10,
    meetsMinPasswordLength: value.length >= 10,
    passwordPolicy: { customStrengthOptions: { minPasswordLength: 10 } } }),
  createWithEmail: async (email) => signed(email.split('@')[0]),
  signInWithEmail: async (email) => signed(email.split('@')[0]),
  signInWithGoogle: async () => signed('google').token,
  getEmailVerificationState: async () => null,
  getToken: async () => read()?.token ?? null,
  getTokenContext: async () => read(),
  observe: async (callback) => { const user = read(); callback(Boolean(user), user?.uid); return () => {} },
  signOut: async () => { localStorage.removeItem(key) },
  getAuthMethods: async () => ['password'],
}
