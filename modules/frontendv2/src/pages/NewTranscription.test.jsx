import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import NewTranscription from './NewTranscription'
import { audioService } from '../services/audioService'
import { useAuthStore } from '../stores/authStore'

vi.mock('../services/audioService', () => ({ audioService: { getProviderSettings: vi.fn(), createTranscriptionJob: vi.fn() } }))
const settings = (available, allowed) => ({
  preferences: { transcription_provider: 'assemblyai', use_diarization: false },
  providers: { whisper: { available: true, allowed: true }, assemblyai: { available, allowed } },
})
beforeEach(() => {
  vi.resetAllMocks()
  useAuthStore.setState({ user: { registration_source: 'local' }, isAuthenticated: true })
})
afterEach(cleanup)

it.each([[true, false], [false, true]])('labels and blocks unavailable AssemblyAI (available=%s, allowed=%s)', async (available, allowed) => {
  audioService.getProviderSettings.mockResolvedValue(settings(available, allowed))
  const { container } = render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  const provider = await screen.findByRole('button', { name: /AssemblyAI/ })
  expect(provider.disabled).toBe(true)
  expect(provider.textContent).toContain('Indisponível')
  fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(['audio'], 'sample.wav', { type: 'audio/wav' })] } })
  expect(screen.getByRole('button', { name: 'Iniciar Transcrição' }).disabled).toBe(true)
  expect(audioService.createTranscriptionJob).not.toHaveBeenCalled()
})

it('keeps AssemblyAI selectable when the server permits it', async () => {
  audioService.getProviderSettings.mockResolvedValue(settings(true, true))
  render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  expect((await screen.findByRole('button', { name: /AssemblyAI/ })).disabled).toBe(false)
  expect(screen.queryByText('Indisponível')).toBeNull()
})

it('shows Guest AssemblyAI as unavailable directly from guest policy', () => {
  useAuthStore.setState({ user: null, isAuthenticated: false })
  render(<MemoryRouter><NewTranscription guestPolicy={{ can_create_job: false, max_upload_mb: 100, max_audio_seconds: 600, unavailable_reason: 'Serviço temporariamente bloqueado.' }} /></MemoryRouter>)
  expect(screen.getByText('Indisponível')).toBeTruthy()
  expect(screen.getByText('Serviço temporariamente bloqueado.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Iniciar Transcrição' }).disabled).toBe(true)
  expect(document.querySelector('input[type="file"]').disabled).toBe(true)
  expect(audioService.getProviderSettings).not.toHaveBeenCalled()
})
