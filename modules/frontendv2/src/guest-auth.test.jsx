import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Guest from './pages/Guest'
import App from './App'
import Login from './pages/Login'
import NewTranscription from './pages/NewTranscription'
import { guestService } from './services/guestService'
import { authService } from './services/authService'
import { useAuthStore } from './stores/authStore'

vi.mock('./services/guestService', () => ({ guestService: {
  policy: vi.fn(), session: vi.fn(), result: vi.fn(), createSession: vi.fn(),
  createJob: vi.fn(), claim: vi.fn(), delete: vi.fn(),
} }))
vi.mock('./services/authService', () => ({ authService: { signup: vi.fn(), login: vi.fn(), me: vi.fn() } }))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() }, Toaster: () => null }))

const policy = { max_upload_mb: 10, max_audio_seconds: 60, jobs_per_session: 1, retention_hours: 24 }
beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  sessionStorage.clear()
  window.history.replaceState({}, '', '/')
  useAuthStore.setState({ user: null, token: null, isAuthenticated: false })
  guestService.policy.mockResolvedValue(policy)
})
afterEach(cleanup)

describe('Guest and account boundaries', () => {
  it('shows server upload limits for public accounts without exposing platform providers', async () => {
    useAuthStore.setState({ user: { registration_source: 'public' }, token: 'test-user-proof', isAuthenticated: true })
    render(<MemoryRouter><NewTranscription /></MemoryRouter>)
    expect(await screen.findByText(/m[aá]x\. 10MB/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /AssemblyAI/ })).toBeNull()
    expect(screen.getByLabelText('Segmentação de Falantes')).toBeTruthy()
  })

  it('does not enable public upload if the server limits are unavailable and supports retry', async () => {
    guestService.policy.mockRejectedValueOnce(new Error('Unavailable'))
    useAuthStore.setState({ user: { registration_source: 'public' }, token: 'test-user-proof', isAuthenticated: true })
    render(<MemoryRouter><NewTranscription /></MemoryRouter>)
    expect(await screen.findByText('Não foi possível consultar os limites de upload.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Iniciar Transcrição' }).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(await screen.findByText(/m[aá]x\. 10MB/)).toBeTruthy()
  })
  it('App root is public without a session or auth bootstrap request', async () => {
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Experimente o USAGI sem conta' })).toBeTruthy()
    expect(authService.me).not.toHaveBeenCalled()
  })

  it('App keeps protected history behind login', async () => {
    window.history.replaceState({}, '', '/meetings')
    render(<App />)
    expect(await screen.findByLabelText('Usuário')).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Reuniões' })).toBeNull()
  })
  it('opens public upload without logging in or creating an identity on page load', async () => {
    render(<MemoryRouter><Guest /></MemoryRouter>)
    expect(await screen.findByText(/Até 10 MiB e 60s/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Criar conta para salvar' })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Faster-Whisper/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /AssemblyAI/ })).toBeNull()
    expect(screen.queryByLabelText('Segmentação de Falantes')).toBeNull()
    expect(guestService.createSession).not.toHaveBeenCalled()
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
      <Route path="/guest" element={<p>Salvar visitante</p>} />
    </Routes></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Usuário'), { target: { value: 'visitor' } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'visitor@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'test password long' } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar conta' }))
    expect(await screen.findByText('Salvar visitante')).toBeTruthy()
    expect(authService.signup).toHaveBeenCalledWith('visitor', 'visitor@example.test', 'test password long')
    expect(useAuthStore.getState().user.registration_source).toBe('public')
  })

  it('does not offer platform AssemblyAI to a newly registered account', () => {
    useAuthStore.setState({ user: { registration_source: 'public' }, isAuthenticated: true })
    render(<MemoryRouter><NewTranscription /></MemoryRouter>)
    expect(screen.queryByRole('button', { name: /AssemblyAI/ })).toBeNull()
    expect(screen.getByLabelText('Segmentação de Falantes')).toBeTruthy()
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
