import { describe, expect, it } from 'vitest'
import { authDestination, authSwitchQuery, safeReturnTo } from './authReturn'

describe('auth return routing', () => {
  it('uses an internal return route and carries it between auth pages', () => {
    const params = new URLSearchParams('returnTo=%2Fhistory%3Fpage%3D2&saveGuest=1&campaign=a')
    expect(authDestination(params)).toBe('/history?page=2')
    expect(authSwitchQuery(params)).toBe('?returnTo=%2Fhistory%3Fpage%3D2&saveGuest=1')
  })

  it('routes guest save through the transcription page', () => {
    expect(authDestination(new URLSearchParams('saveGuest=1'))).toBe('/new-transcription?saveGuest=1')
  })

  it.each(['https://evil.test', '//evil.test/path', '/\\evil.test', '/login?x=1', '/signup'])('rejects unsafe return path %s', (value) => {
    expect(safeReturnTo(value)).toBeNull()
  })
})
