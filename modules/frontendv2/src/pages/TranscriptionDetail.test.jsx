import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import TranscriptionDetail from './TranscriptionDetail'
import { audioService } from '../services/audioService'

vi.mock('../services/audioService', () => ({ audioService: { getTranscription: vi.fn() } }))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }))

beforeEach(() => vi.resetAllMocks())

describe('TranscriptionDetail loading', () => {
  it('keeps the page available and retries after a request failure', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    audioService.getTranscription.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({
      id: 8, filename: 'call.wav', status: 'completed', created_at: '2026-10-02T10:00:00Z',
      duration_seconds: 4, word_count: 1, num_speakers: 1,
      segments: [{ speaker: 'SPEAKER_00', start: 0, end: 4, text: 'hello' }],
    })
    render(<MemoryRouter initialEntries={['/transcriptions/8']}><Routes>
      <Route path="/transcriptions/:id" element={<TranscriptionDetail />} />
      <Route path="/transcriptions" element={<p>History page</p>} />
    </Routes></MemoryRouter>)
    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeTruthy()
    expect(screen.queryByText('History page')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(await screen.findByRole('heading', { name: 'call.wav' })).toBeTruthy()
    await waitFor(() => expect(audioService.getTranscription).toHaveBeenCalledTimes(2))
  })
})
