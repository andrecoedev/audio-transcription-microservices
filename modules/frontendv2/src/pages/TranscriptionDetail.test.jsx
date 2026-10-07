import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import TranscriptionDetail from './TranscriptionDetail'
import { audioService } from '../services/audioService'

vi.mock('../services/audioService', () => ({ audioService: { getTranscription: vi.fn() } }))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }))

beforeEach(() => vi.resetAllMocks())
afterEach(cleanup)

describe('TranscriptionDetail loading', () => {
  it('keeps long filenames and the statistics grid in the shared page container', async () => {
    const filename = `${'reuniao_de_planejamento_'.repeat(6)}.wav`
    audioService.getTranscription.mockResolvedValue({ id: 8, filename, status: 'completed', created_at: '2026-10-02T10:00:00Z', segments: [] })
    render(<MemoryRouter initialEntries={['/transcriptions/8']}><Routes><Route path="/transcriptions/:id" element={<TranscriptionDetail />} /></Routes></MemoryRouter>)
    const heading = await screen.findByRole('heading', { name: filename })
    const grid = screen.getByLabelText('Informações da transcrição')
    expect(grid.parentElement.className).toContain('max-w-6xl')
    expect(heading.className).toContain('break-all')
    expect(grid.className).toContain('sm:grid-cols-2')
    expect(grid.className).toContain('xl:grid-cols-4')
    expect(grid.parentElement.contains(heading)).toBe(true)
  })

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

  it.each(['queued', 'processing'])('renders a focused real-status view for %s jobs', async (status) => {
    audioService.getTranscription.mockResolvedValue({
      id: 9, filename: 'review.m4a', status, created_at: '2026-10-03T10:00:00Z',
      duration_seconds: 52 * 60, word_count: null, num_speakers: null, segments: [],
    })
    render(<MemoryRouter initialEntries={['/transcriptions/9']}><Routes>
      <Route path="/transcriptions/:id" element={<TranscriptionDetail />} />
    </Routes></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Transcrevendo áudio' })).toBeTruthy()
    expect(screen.getByText('review.m4a · 52 minutos e 0 segundos')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Voltar ao histórico/ })).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Status do processamento' })).toBeTruthy()
    expect(screen.queryByText('Palavras')).toBeNull()
    expect(screen.queryByText('Falantes')).toBeNull()
    expect(screen.queryByRole('button', { name: 'TXT' })).toBeNull()
    expect(screen.queryByText('Transcrição completa')).toBeNull()
  })
})
