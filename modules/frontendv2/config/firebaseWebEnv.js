// Only these public Firebase Web fields may cross the build/client boundary.
const WEB_FIELDS = ['API_KEY', 'AUTH_DOMAIN', 'PROJECT_ID', 'APP_ID']

export function firebaseWebEnv(...sources) {
  const env = Object.assign({}, ...sources)
  return Object.fromEntries(WEB_FIELDS.map((field) => {
    const key = `VITE_FIREBASE_${field}`
    // Non-empty canonical VITE values override the compatibility aliases.
    const canonical = typeof env[key] === 'string' ? env[key].trim() : ''
    const value = canonical || env[`FIREBASE_${field}`] || ''
    return [key, typeof value === 'string' ? value.trim() : '']
  }))
}
