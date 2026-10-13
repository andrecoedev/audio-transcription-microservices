import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Meetings from './Meetings'
import { audioService } from '../services/audioService'

vi.mock('../services/audioService', () => ({ audioService: {
  listMeetings: vi.fn(), deleteMeeting: vi.fn(),
} }))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }))
import toast from 'react-hot-toast'

beforeEach(() => {
  vi.resetAllMocks()
  audioService.listMeetings.mockResolvedValue({ total: 1, meetings: [{
    id: 12, title: 'Planning sync', status: 'completed', created_at: '2026-10-02T10:00:00Z',
    duration_seconds: 75, speaker_count: 3,
  }] })
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Meetings history', () => {
  it('presents persisted meetings as a table with their actual metadata', async () => {
    render(<MemoryRouter><Meetings /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: 'Planning sync' })).toBeTruthy()
    const row = screen.getByRole('row', { name: /Planning sync/ })
    expect(row.textContent).toContain('3')
    expect(row.textContent).toContain('3 falantes')
    expect(row.textContent).toContain('1 minuto e 15 segundos')
    expect(row.textContent).toContain('Concluída')
  })

  it('preserves confirmation and delete API behavior', async () => {
    audioService.deleteMeeting.mockResolvedValue({ cleanup_pending: false })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<MemoryRouter><Meetings /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Excluir' }))
    await waitFor(() => expect(audioService.deleteMeeting).toHaveBeenCalledWith(12))
    expect(toast.success).toHaveBeenCalledWith('Reunião excluída')
    expect(audioService.listMeetings).toHaveBeenCalledTimes(2)
  })

  it('reports pending file cleanup after deleting a meeting', async () => {
    audioService.deleteMeeting.mockResolvedValue({ cleanup_pending: true })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<MemoryRouter><Meetings /></MemoryRouter>)

    fireEvent.click(await screen.findByRole('button', { name: 'Excluir' }))

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(
      'Reunião excluída. A remoção dos arquivos está pendente e será tentada novamente.',
    ))
  })

  it('does not request deletion when the confirmation is canceled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<MemoryRouter><Meetings /></MemoryRouter>)

    fireEvent.click(await screen.findByRole('button', { name: 'Excluir' }))

    expect(audioService.deleteMeeting).not.toHaveBeenCalled()
  })
})
