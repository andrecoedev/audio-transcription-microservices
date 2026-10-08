import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Guest from './pages/Guest'
import GuestDemo from './pages/GuestDemo'
import App from './App'
import Login from './pages/Login'
import NewTranscription from './pages/NewTranscription'
import { guestService } from './services/guestService'
import { authService } from './services/authService'
import { useAuthStore } from './stores/authStore'
import { audioService } from './services/audioService'

vi.mock('./services/guestService', () => ({ guestService: {
  policy: vi.fn(), demo: vi.fn(), session: vi.fn(), result: vi.fn(), createSession: vi.fn(),
  createJob: vi.fn(), claim: vi.fn(), delete: vi.fn(),
} }))
vi.mock('./services/authService', () => ({ authService: { signup: vi.fn(), login: vi.fn(), me: vi.fn(), getConfig: vi.fn() } }))
vi.mock('./services/audioService', () => ({ audioService: {
  getProviderSettings: vi.fn(), createTranscriptionJob: vi.fn(),
} }))
vi.mock('./pages/Dashboard', () => ({ default: () => <h1>Experiência autenticada</h1> }))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() }, Toaster: () => null }))

const policy = { allowed_extensions: ['wav', 'mp3', 'm4a'], max_upload_mb: 100, max_audio_seconds: 600, jobs_per_session: 1, retention_hours: 24,
  provider: 'assemblyai', diarization: true, can_create_job: false, unavailable_reason: 'Serviço em validação.' }
beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  sessionStorage.clear()
  window.history.replaceState({}, '', '/')
  useAuthStore.setState({ user: null, token: null, authProvider: 'local', isAuthenticated: false })
  authService.getConfig.mockResolvedValue({ firebase_enabled: false, local_signup_enabled: true })
  guestService.policy.mockResolvedValue(policy)
  guestService.demo.mockResolvedValue({
    id: 'usagi-demo-v1', is_demo: true, title: 'Reunião de exemplo', description: 'Demonstração sintética.', duration_seconds: 90,
    speakers: [{ id: 'SPEAKER_00', display_name: 'Falante 1' }],
    segments: [{ order: 0, start: 0, end: 15, speaker: 'SPEAKER_00', text: 'Trecho sintético.' }],
    intelligence: { schema_version: '1', summary: 'Resumo sintético.', topics: [], decisions: [], action_items: [], open_questions: [] },
  })
  audioService.getProviderSettings.mockResolvedValue({
    preferences: { transcription_provider: 'automatic', intelligence_provider: 'automatic', use_diarization: true },
    credential_storage_available: true,
    providers: {
      whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
      assemblyai: { available: true, allowed: false, configured: false, credential_source: null },
      gemini: { available: true, allowed: false, configured: false, credential_source: null },
    },
    credentials: { assemblyai: { configured: false, updated_at: null }, gemini: { configured: false, updated_at: null } },
  })
})
afterEach(cleanup)

describe('Guest and account boundaries', () => {
  it.each([false, true])('immediately enters the authenticated app after signup=%s and preserves pending ownership proof on refresh', async (signup) => {
    sessionStorage.setItem('usagi-guest-session', JSON.stringify({ guest_token: 'synthetic-proof', resultId: 7 }))
    guestService.result.mockResolvedValue({ status: 'completed', segments: [] })
    const response = { access_token: 'synthetic-user-proof', user: { username: 'visitor', registration_source: 'public' } }
    authService.login.mockResolvedValue(response)
    authService.signup.mockResolvedValue(response)
    authService.me.mockResolvedValue({ authenticated: true, user: response.user })
    window.history.replaceState({}, '', signup ? '/signup?saveGuest=1' : '/login?saveGuest=1')
    render(<App />)
    fireEvent.change(await screen.findByLabelText('Usuário'), { target: { value: 'visitor' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'test password long' } })
    if (signup) fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'visitor@example.test' } })
    fireEvent.click(screen.getByRole('button', { name: signup ? 'Criar conta' : 'Entrar' }))
    expect(await screen.findByRole('heading', { name: 'Nova Transcrição' })).toBeTruthy()
    expect(window.location.pathname).toBe('/new-transcription')
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(await screen.findByRole('button', { name: 'Salvar na minha conta' })).toBeTruthy()
    expect(guestService.claim).not.toHaveBeenCalled()
    cleanup()
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Nova Transcrição' })).toBeTruthy()
    expect(sessionStorage.getItem('usagi-guest-session')).not.toBeNull()
  })
  it('shows server upload limits and keeps platform-only providers disabled for public accounts', async () => {
    useAuthStore.setState({ user: { registration_source: 'public' }, token: 'test-user-proof', isAuthenticated: true })
    render(<MemoryRouter><NewTranscription /></MemoryRouter>)
    expect(await screen.findByText((_, element) => element.textContent === 'Máximo de 100 MB por arquivo')).toBeTruthy()
    expect(screen.getByRole('button', { name: /AssemblyAI/ }).disabled).toBe(true)
    expect(screen.getByLabelText('Detecção de falantes')).toBeTruthy()
  })

  it('does not enable public upload if the server limits are unavailable and supports retry', async () => {
    guestService.policy.mockRejectedValueOnce(new Error('Unavailable'))
    useAuthStore.setState({ user: { registration_source: 'public' }, token: 'test-user-proof', isAuthenticated: true })
    render(<MemoryRouter><NewTranscription /></MemoryRouter>)
    expect(await screen.findByText('Não foi possível consultar os limites e formatos de upload.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Iniciar Transcrição' }).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(await screen.findByText((_, element) => element.textContent === 'Máximo de 100 MB por arquivo')).toBeTruthy()
  })
  it('App root is public without a session or auth bootstrap request', async () => {
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Início' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Iniciar Transcrição' })).toBeNull()
    expect(document.querySelector('input[type="file"]')).toBeNull()
    expect(screen.getByRole('link', { name: 'Ver demonstração' }).getAttribute('href')).toBe('/new-transcription')
    expect(screen.getByRole('complementary')).toBeTruthy()
    expect(authService.me).not.toHaveBeenCalled()
    expect(guestService.policy).not.toHaveBeenCalled()
  })

  it('opens the synthetic demo without exposing upload or creating a guest session/job', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('link', { name: 'Ver demonstração' }))
    expect(await screen.findByRole('heading', { name: 'Demonstração interativa' })).toBeTruthy()
    expect(await screen.findByText('Reunião de exemplo')).toBeTruthy()
    expect(document.querySelector('input[type="file"]')).toBeNull()
    expect(window.location.pathname).toBe('/new-transcription')
    expect(guestService.createSession).not.toHaveBeenCalled()
    expect(guestService.createJob).not.toHaveBeenCalled()
  })

  it('App keeps protected history behind login', async () => {
    window.history.replaceState({}, '', '/meetings')
    render(<App />)
    expect(await screen.findByText('Salve e acompanhe suas reuniões')).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Reuniões' })).toBeNull()
  })
  it('opens the public demo without upload, policy lookup, or creating an identity', async () => {
    render(<MemoryRouter><GuestDemo /></MemoryRouter>)
    expect(await screen.findByText('Reunião de exemplo')).toBeTruthy()
    expect(document.querySelector('input[type="file"]')).toBeNull()
    expect(guestService.createSession).not.toHaveBeenCalled()
    expect(guestService.createJob).not.toHaveBeenCalled()
    expect(guestService.policy).not.toHaveBeenCalled()
    expect(audioService.getProviderSettings).not.toHaveBeenCalled()
  })

  it('restores result using the guest proof and transfers it only with explicit authenticated action', async () => {
    sessionStorage.setItem('usagi-guest-session', JSON.stringify({ guest_token: 'test-guest-proof', resultId: 7 }))
    useAuthStore.setState({ isAuthenticated: true, token: 'test-user-proof' })
    guestService.result.mockResolvedValue({ id: 7, status: 'completed', segments: [{ start: 0, end: 1, text: 'Resultado sintético' }] })
    guestService.claim.mockResolvedValue({ transferred: 1 })
    render(<MemoryRouter><Routes>
      <Route path="/" element={<Guest />} />
      <Route path="/transcriptions/7" element={<p>Resultado na conta</p>} />
    </Routes></MemoryRouter>)
    expect(await screen.findByText(/Resultado sintético/)).toBeTruthy()
    expect(guestService.result).toHaveBeenCalledWith('test-guest-proof', 7)
    expect(guestService.claim).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Salvar na minha conta' }))
    expect(await screen.findByText('Resultado na conta')).toBeTruthy()
    expect(guestService.claim).toHaveBeenCalledWith('test-guest-proof')
    expect(sessionStorage.getItem('usagi-guest-session')).toBeNull()
  })

  it('does not delete an active guest job', async () => {
    sessionStorage.setItem('usagi-guest-session', JSON.stringify({ guest_token: 'proof', resultId: 7 }))
    guestService.result.mockResolvedValue({ status: 'processing', segments: [] })
    render(<MemoryRouter><Guest /></MemoryRouter>)
    expect((await screen.findByRole('button', { name: 'Excluir resultado temporário' })).disabled).toBe(true)
    expect(guestService.delete).not.toHaveBeenCalled()
  })

  it('reports expiry and discards unusable guest proof without logging out the account', async () => {
    sessionStorage.setItem('usagi-guest-session', JSON.stringify({ guest_token: 'proof', resultId: 7 }))
    useAuthStore.setState({ isAuthenticated: true, token: 'user-proof' })
    guestService.result.mockRejectedValue(Object.assign(new Error('expired'), { status: 401 }))
    render(<MemoryRouter><Guest /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(sessionStorage.getItem('usagi-guest-session')).toBeNull()
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
  })

  it('creates a public account and returns to the explicit guest save flow', async () => {
    authService.signup.mockResolvedValue({ access_token: 'user-proof', user: { username: 'visitor', registration_source: 'public' } })
    render(<MemoryRouter initialEntries={['/signup?saveGuest=1']}><Routes>
      <Route path="/signup" element={<Login signup />} />
      <Route path="/new-transcription" element={<p>Experiência autenticada</p>} />
    </Routes></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('Usuário'), { target: { value: 'visitor' } })
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'visitor@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'test password long' } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar conta' }))
    expect(await screen.findByText('Experiência autenticada')).toBeTruthy()
    expect(authService.signup).toHaveBeenCalledWith('visitor', 'visitor@example.test', 'test password long')
    expect(useAuthStore.getState().user.registration_source).toBe('public')
  })

  it('keeps platform AssemblyAI unavailable to a newly registered account', async () => {
    useAuthStore.setState({ user: { registration_source: 'public' }, isAuthenticated: true })
    render(<MemoryRouter><NewTranscription /></MemoryRouter>)
    expect((await screen.findByRole('button', { name: /AssemblyAI/ })).disabled).toBe(true)
    expect(screen.getByLabelText('Detecção de falantes')).toBeTruthy()
  })

  it('offers account-owned AssemblyAI when server settings allow it', async () => {
    useAuthStore.setState({ user: { registration_source: 'public' }, token: 'test-user-proof', isAuthenticated: true })
    audioService.getProviderSettings.mockResolvedValueOnce({
      preferences: { transcription_provider: 'automatic', intelligence_provider: 'automatic', use_diarization: true },
      credential_storage_available: true,
      providers: {
        whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
        assemblyai: { available: true, allowed: true, configured: true, credential_source: 'user' },
        gemini: { available: true, allowed: true, configured: true, credential_source: 'user' },
      },
      credentials: { assemblyai: { configured: true, updated_at: null }, gemini: { configured: true, updated_at: null } },
    })
    render(<MemoryRouter><NewTranscription /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: /AssemblyAI/ })).toBeTruthy()
    expect(screen.getByLabelText('Detecção de falantes').checked).toBe(true)
  })

  it('preserves failed conversion proof so the user can retry', async () => {
    sessionStorage.setItem('usagi-guest-session', JSON.stringify({ guest_token: 'proof', resultId: 7 }))
    useAuthStore.setState({ isAuthenticated: true })
    guestService.result.mockResolvedValue({ status: 'completed', segments: [] })
    guestService.claim.mockRejectedValue(new Error('Service unavailable'))
    render(<MemoryRouter><Guest /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Salvar na minha conta' }))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Service unavailable'))
    expect(sessionStorage.getItem('usagi-guest-session')).not.toBeNull()
  })
})
