import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Meetings from './Meetings'
import { audioService } from '../services/audioService'

vi.mock('../services/audioService', () => ({ audioService: {
  listMeetings: vi.fn(), deleteMeeting: vi.fn(),
} }))

beforeEach(() => {
  vi.resetAllMocks()
  audioService.listMeetings.mockResolvedValue({ total: 1, meetings: [{
    id: 12, title: 'Planning sync', status: 'completed', created_at: '2026-10-02T10:00:00Z',
    duration_seconds: 75, speaker_count: 3,
  }] })
})
afterEach(cleanup)

describe('Meetings history', () => {
  it('presents persisted meetings as a table with their actual metadata', async () => {
    render(<MemoryRouter><Meetings /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: 'Planning sync' })).toBeTruthy()
    const row = screen.getByRole('row', { name: /Planning sync/ })
    expect(row.textContent).toContain('3')
    expect(row.textContent).toContain('1 minuto e 15 segundos')
    expect(row.textContent).toContain('Concluída')
  })

  it('preserves confirmation and delete API behavior', async () => {
    audioService.deleteMeeting.mockResolvedValue({})
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<MemoryRouter><Meetings /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Excluir' }))
    await waitFor(() => expect(audioService.deleteMeeting).toHaveBeenCalledWith(12))
    expect(audioService.listMeetings).toHaveBeenCalledTimes(2)
  })
})
