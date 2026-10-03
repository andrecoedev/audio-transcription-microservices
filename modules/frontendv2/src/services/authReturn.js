const AUTH_PATHS = new Set(['/login', '/signup'])

export function safeReturnTo(value) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return null
  try {
    const parsed = new URL(value, 'https://usagi.invalid')
    if (parsed.origin !== 'https://usagi.invalid' || AUTH_PATHS.has(parsed.pathname)) return null
    return `${parsed.pathname}${parsed.search}${parsed.hash}`
  } catch {
    return null
  }
}

export function authDestination(searchParams) {
  const returnTo = safeReturnTo(searchParams.get('returnTo'))
  if (returnTo) return returnTo
  if (searchParams.get('saveGuest') === '1') return '/new-transcription?saveGuest=1'
  return '/'
}

export function authSwitchQuery(searchParams) {
  const query = new URLSearchParams()
  const returnTo = safeReturnTo(searchParams.get('returnTo'))
  if (returnTo) query.set('returnTo', returnTo)
  if (searchParams.get('saveGuest') === '1') query.set('saveGuest', '1')
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}
