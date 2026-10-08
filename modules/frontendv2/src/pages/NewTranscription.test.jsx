import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import NewTranscription from './NewTranscription'
import { audioService } from '../services/audioService'
import { guestService } from '../services/guestService'
import { useAuthStore } from '../stores/authStore'
import userEvent from '@testing-library/user-event'
import toast from 'react-hot-toast'

vi.mock('../services/audioService', () => ({ audioService: { getProviderSettings: vi.fn(), createTranscriptionJob: vi.fn() } }))
vi.mock('../services/guestService', () => ({ guestService: { policy: vi.fn() } }))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }))
const policy = { allowed_extensions: ['wav', 'mp3', 'm4a'], max_upload_mb: 100, max_audio_seconds: 600 }
const settings = (available, allowed) => ({
  preferences: { transcription_provider: 'assemblyai', use_diarization: false },
  providers: { whisper: { available: true, allowed: true }, assemblyai: { available, allowed } },
})
beforeEach(() => {
  vi.resetAllMocks()
  guestService.policy.mockResolvedValue(policy)
  audioService.getProviderSettings.mockResolvedValue(settings(true, true))
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
  render(<MemoryRouter><NewTranscription guestPolicy={{ ...policy, can_create_job: false, unavailable_reason: 'Serviço temporariamente bloqueado.' }} /></MemoryRouter>)
  expect(screen.getByText('Indisponível')).toBeTruthy()
  expect(screen.getByText('Serviço temporariamente bloqueado.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Iniciar Transcrição' }).disabled).toBe(true)
  expect(document.querySelector('input[type="file"]').disabled).toBe(true)
  expect(audioService.getProviderSettings).not.toHaveBeenCalled()
})

it('advertises exactly the formats returned by server policy', async () => {
  guestService.policy.mockResolvedValue({ ...policy, allowed_extensions: ['wav', 'm4a'] })
  render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  await screen.findByText('WAV, M4A')
  const input = document.querySelector('input[type="file"]')
  expect(input.getAttribute('accept')).toContain('.wav')
  expect(input.getAttribute('accept')).toContain('.m4a')
  expect(input.getAttribute('accept')).not.toContain('.ogg')
  expect(input.getAttribute('accept')).not.toContain('.aac')
  expect(screen.getByText('WAV, M4A')).toBeTruthy()
})

it('accepts M4A with video/mp4 MIME when the extension is allowed', async () => {
  guestService.policy.mockResolvedValue({ ...policy, allowed_extensions: ['m4a'] })
  audioService.getProviderSettings.mockResolvedValue(settings(true, true))
  audioService.createTranscriptionJob.mockResolvedValue({ id: 12 })
  render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  await screen.findByText(/Formatos disponíveis: M4A/)
  await userEvent.upload(document.querySelector('input[type="file"]'), new File(['audio'], 'recording.m4a', { type: 'video/mp4' }))
  expect(screen.getByText('recording.m4a')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar Transcrição' }))
  expect(await screen.findByText('recording.m4a')).toBeTruthy()
  expect(audioService.createTranscriptionJob).toHaveBeenCalledOnce()
})

it.each([
  ['aac', 'audio/aac'],
  ['ogg', 'audio/ogg'],
])('rejects .%s before creating a job when server policy omits that extension', async (extension, mimeType) => {
  guestService.policy.mockResolvedValue({ ...policy, allowed_extensions: ['wav', 'm4a'] })
  render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  await screen.findByText(/Formatos disponíveis: WAV, M4A/)
  await userEvent.upload(document.querySelector('input[type="file"]'), new File(['audio'], `recording.${extension}`, { type: mimeType }), { applyAccept: false })
  expect(audioService.createTranscriptionJob).not.toHaveBeenCalled()
  expect(screen.queryByText(`recording.${extension}`)).toBeNull()
  expect(toast.error).toHaveBeenCalled()
})
