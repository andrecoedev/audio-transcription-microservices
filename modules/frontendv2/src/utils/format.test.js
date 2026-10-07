import { describe, expect, it } from 'vitest'
import { formatCount, formatDuration, formatNumber, formatTimestamp } from './format'

describe('presentation of API metadata', () => {
  it('formats numbers and counts for Brazilian Portuguese', () => {
    expect(formatNumber(1234)).toBe('1.234')
    expect(formatCount(1, 'falante', 'falantes')).toBe('1 falante')
    expect(formatCount(2, 'falante', 'falantes')).toBe('2 falantes')
    expect(formatCount(0, 'falante', 'falantes')).toBe('0 falantes')
    expect(formatCount(null, 'falante', 'falantes')).toBe('—')
  })
  it('distinguishes missing durations from zero and supports long recordings', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(0)).toBe('0 segundos')
    expect(formatDuration(60)).toBe('1 minuto e 0 segundos')
    expect(formatDuration(3660)).toBe('1 hora e 1 minuto')
  })
  it('does not invent dates when metadata is missing or invalid', () => {
    expect(formatTimestamp(null)).toBe('—')
    expect(formatTimestamp('invalid')).toBe('—')
    expect(formatTimestamp('2026-10-03T12:00:00Z')).toContain('2026')
  })
})
