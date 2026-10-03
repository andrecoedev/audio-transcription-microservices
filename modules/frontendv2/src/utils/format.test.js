import { describe, expect, it } from 'vitest'
import { formatDuration, formatTimestamp } from './format'

describe('presentation of API metadata', () => {
  it('distinguishes missing durations from zero and supports long recordings', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(0)).toBe('0min 0s')
    expect(formatDuration(3660)).toBe('1h 1min')
  })
  it('does not invent dates when metadata is missing or invalid', () => {
    expect(formatTimestamp(null)).toBe('—')
    expect(formatTimestamp('invalid')).toBe('—')
    expect(formatTimestamp('2026-10-03T12:00:00Z')).toContain('2026')
  })
})
