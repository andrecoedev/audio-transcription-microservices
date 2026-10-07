import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Transcriptions from './Transcriptions'
import { audioService } from '../services/audioService'

vi.mock('../services/audioService', () => ({ audioService: {
  listTranscriptions: vi.fn(), deleteTranscription: vi.fn(),
} }))

beforeEach(() => {
  vi.resetAllMocks()
  audioService.listTranscriptions.mockResolvedValue({ total: 2, transcriptions: [
    { id: 1, filename: 'team-sync.wav', status: 'completed', created_at: '2026-10-02T10:00:00Z', duration_seconds: 125, word_count: 30, num_speakers: 2 },
    { id: 2, filename: 'interview.mp3', status: 'queued', created_at: '2026-10-01T10:00:00Z' },
  ] })
})
afterEach(cleanup)

describe('Transcriptions history', () => {
  it('renders actual rows and filters visible page results by filename', async () => {
    render(<MemoryRouter><Transcriptions /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: 'team-sync.wav' })).toBeTruthy()
    expect(screen.getByRole('row', { name: /interview\.mp3/ }).textContent).toContain('Na fila')
    fireEvent.change(screen.getByPlaceholderText('Buscar por nome do arquivo...'), { target: { value: 'interview' } })
    expect(screen.queryByRole('link', { name: 'team-sync.wav' })).toBeNull()
    expect(screen.getByRole('link', { name: 'interview.mp3' })).toBeTruthy()
  })

  it('shows and searches by the original Unicode filename instead of the storage key', async () => {
    audioService.listTranscriptions.mockResolvedValue({ total: 1, transcriptions: [
      { id: 3, filename: `${'a'.repeat(32)}.wav`, original_filename: 'Reunião da equipe.wav', status: 'completed', created_at: '2026-10-02T10:00:00Z' },
    ] })
    render(<MemoryRouter><Transcriptions /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: 'Reunião da equipe.wav' })).toBeTruthy()
    fireEvent.change(screen.getByPlaceholderText('Buscar por nome do arquivo...'), { target: { value: 'reunião' } })
    expect(screen.getByRole('link', { name: 'Reunião da equipe.wav' })).toBeTruthy()
  })

  it('passes status filter to API and resets server pagination', async () => {
    audioService.listTranscriptions.mockResolvedValue({ total: 42, transcriptions: [
      { id: 1, filename: 'team-sync.wav', status: 'completed', created_at: '2026-10-02T10:00:00Z' },
    ] })
    render(<MemoryRouter><Transcriptions /></MemoryRouter>)
    await screen.findByRole('link', { name: 'team-sync.wav' })
    fireEvent.click(screen.getByRole('button', { name: 'Próxima' }))
    await waitFor(() => expect(audioService.listTranscriptions).toHaveBeenLastCalledWith({ skip: 10, limit: 10, status: undefined }))
    fireEvent.change(screen.getByLabelText('Filtrar por status'), { target: { value: 'queued' } })
    await waitFor(() => expect(audioService.listTranscriptions).toHaveBeenLastCalledWith({ skip: 0, limit: 10, status: 'queued' }))
  })

  it('shows a recoverable load error and retries', async () => {
    audioService.listTranscriptions.mockRejectedValueOnce(new Error('offline'))
    render(<MemoryRouter><Transcriptions /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(await screen.findByRole('link', { name: 'team-sync.wav' })).toBeTruthy()
  })
})
