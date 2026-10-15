import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  credential_storage_available: true,
  credentials: { assemblyai: { configured: allowed } },
  providers: { whisper: { available: true, allowed: true }, assemblyai: { available, allowed, platform_access: available && allowed, byok_allowed: allowed } },
})
beforeEach(() => {
  vi.resetAllMocks()
  guestService.policy.mockResolvedValue(policy)
  audioService.getProviderSettings.mockResolvedValue(settings(true, true))
  useAuthStore.setState({ user: { registration_source: 'local' }, isAuthenticated: true })
})
afterEach(cleanup)

it('uses each authenticated account upload policy while guests keep their guest limit', async () => {
  const authenticatedPolicy = { ...policy, max_upload_mb: 5120 }
  audioService.getProviderSettings.mockResolvedValue({ ...settings(true, true), upload_policy: authenticatedPolicy })
  useAuthStore.setState({ user: { registration_source: 'public' }, isAuthenticated: true })
  const publicAccount = render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  expect((await screen.findByLabelText('Limites desta conta')).textContent).toContain('5.120')
  publicAccount.unmount()

  useAuthStore.setState({ user: null, isAuthenticated: false })
  const guest = render(<MemoryRouter><NewTranscription guestPolicy={policy} /></MemoryRouter>)
  expect(screen.getByLabelText('Limites desta conta').textContent).toContain('100')
  expect(screen.queryByText(/Acesso de desenvolvimento/)).toBeNull()
  guest.unmount()

  audioService.getProviderSettings.mockResolvedValue({ ...settings(true, true), upload_policy: policy })
  useAuthStore.setState({ user: { registration_source: 'public' }, isAuthenticated: true })
  render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  expect((await screen.findByLabelText('Limites desta conta')).textContent).toContain('100')
})

it('falls back to public limits when an older provider settings response omits upload_policy', async () => {
  audioService.getProviderSettings.mockResolvedValue(settings(true, true))
  useAuthStore.setState({ user: { registration_source: 'public' }, isAuthenticated: true })
  render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  expect((await screen.findByLabelText('Limites desta conta')).textContent).toContain('100')
})

it('identifies development access while presenting upload and duration values as technical caps', async () => {
  audioService.getProviderSettings.mockResolvedValue({
    ...settings(true, true),
    upload_policy: { ...policy, development_access: true, max_upload_mb: 5120, max_audio_seconds: 86400 },
  })

  render(<MemoryRouter><NewTranscription /></MemoryRouter>)

  expect(await screen.findByText('Acesso de desenvolvimento para transcrição local. Os limites abaixo são tetos técnicos; serviços externos mantêm suas permissões e limites.')).toBeTruthy()
  expect(screen.getByLabelText('Limites desta conta').textContent).toContain('Teto técnico 5.120 MB por arquivo')
  expect(screen.getByLabelText('Limites desta conta').textContent).toContain('Até 1.440 minutos de áudio (teto técnico)')
  expect(screen.getByText('Tetos técnicos de envio')).toBeTruthy()
  expect(screen.getByText(/Até 5\.120 MB e 1\.440 minutos por áudio \(teto técnico\)/)).toBeTruthy()
  expect(screen.queryByText(/Sem limite comercial/)).toBeNull()
})

it.each([[true, false], [false, true]])('labels and blocks unavailable AssemblyAI (available=%s, allowed=%s)', async (available, allowed) => {
  audioService.getProviderSettings.mockResolvedValue(settings(available, allowed))
  const { container } = render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  const platformChoice = await screen.findByRole('button', { name: 'Transcrição do Beta' })
  const ownChoice = screen.getByRole('button', { name: 'Minha conta AssemblyAI' })
  expect(platformChoice.disabled).toBe(true)
  expect(ownChoice.disabled).toBe(true)
  expect(platformChoice.textContent).toContain('Indisponível')
  fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(['audio'], 'sample.wav', { type: 'audio/wav' })] } })
  expect(screen.getByRole('button', { name: 'Iniciar Transcrição' }).disabled).toBe(true)
  expect(audioService.createTranscriptionJob).not.toHaveBeenCalled()
})

it('keeps AssemblyAI selectable when the server permits it', async () => {
  audioService.getProviderSettings.mockResolvedValue(settings(true, true))
  render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  expect((await screen.findByRole('button', { name: 'Minha conta AssemblyAI' })).disabled).toBe(false)
  expect(screen.queryByText('Indisponível')).toBeNull()
  expect(screen.getByText(/o áudio necessário ao processamento é enviado ao serviço selecionado/i)).toBeTruthy()
})

it('offers separate beta and own-account routes and submits the selected source explicitly', async () => {
  audioService.getProviderSettings.mockResolvedValue(settings(true, true))
  audioService.createTranscriptionJob.mockResolvedValue({ id: 23 })
  render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  const betaChoice = await screen.findByRole('button', { name: /Transcrição do Beta/ })
  const ownChoice = screen.getByRole('button', { name: /Minha conta AssemblyAI/ })
  expect(betaChoice.disabled).toBe(false)
  expect(ownChoice.disabled).toBe(false)

  await userEvent.upload(document.querySelector('input[type="file"]'), new File(['audio'], 'sample.wav', { type: 'audio/wav' }))
  fireEvent.click(betaChoice)
  expect(screen.getByLabelText('Detecção de falantes').checked).toBe(true)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Iniciar Transcrição' }).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar Transcrição' }))
  await waitFor(() => expect(audioService.createTranscriptionJob).toHaveBeenCalledOnce())
  expect(audioService.createTranscriptionJob.mock.calls[0][1]).toMatchObject({ transcriptionModel: 'assemblyai', credentialSource: 'platform', useDiarization: true })
})

it('blocks the beta route when platform access is unavailable even if another source is permitted', async () => {
  audioService.getProviderSettings.mockResolvedValue({
    ...settings(true, true),
    providers: { whisper: { available: true, allowed: true }, assemblyai: { available: true, allowed: true, platform_access: false, byok_allowed: true } },
  })
  render(<MemoryRouter><NewTranscription /></MemoryRouter>)
  expect((await screen.findByRole('button', { name: /Transcrição do Beta/ })).disabled).toBe(true)
  expect(screen.getByRole('button', { name: /Minha conta AssemblyAI/ }).disabled).toBe(false)
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
  fireEvent.click(screen.getByRole('button', { name: 'Minha conta AssemblyAI' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Iniciar Transcrição' }).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Iniciar Transcrição' }))
  await waitFor(() => expect(audioService.createTranscriptionJob).toHaveBeenCalledOnce())
  expect(audioService.createTranscriptionJob.mock.calls[0][1]).toMatchObject({ credentialSource: 'user' })
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
