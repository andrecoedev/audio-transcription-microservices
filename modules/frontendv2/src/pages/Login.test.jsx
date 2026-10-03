import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Login from './Login'
import { authService } from '../services/authService'
import { useAuthStore } from '../stores/authStore'
import { firebaseAuth } from '../services/firebaseAuth'

vi.mock('../services/authService', () => ({ authService: { signup: vi.fn(), login: vi.fn(), getConfig: vi.fn(), firebaseLogin: vi.fn() } }))
vi.mock('../services/firebaseAuth', () => ({ firebaseAuth: { isConfigured: vi.fn(), projectId: vi.fn(), signInWithGoogle: vi.fn(), signOut: vi.fn() } }))

beforeEach(() => {
  vi.resetAllMocks()
  authService.getConfig.mockResolvedValue({ firebase_enabled: false, firebase_project_id: null, local_signup_enabled: true })
  firebaseAuth.isConfigured.mockReturnValue(false)
  firebaseAuth.projectId.mockReturnValue(null)
  useAuthStore.setState({ setSession: vi.fn(), setFirebaseSession: vi.fn() })
})
afterEach(cleanup)

describe('Login', () => {
  it('uses the in-app save-work card without adding an application shell', () => {
    render(<MemoryRouter><Login /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Salve seu trabalho' })).toBeTruthy()
    expect(screen.getByLabelText('Usuário').getAttribute('autocomplete')).toBe('username')
    expect(screen.getByLabelText('Senha').getAttribute('autocomplete')).toBe('current-password')
    expect(screen.queryByRole('complementary')).toBeNull()
    expect(screen.queryByRole('link', { name: 'USAGI' })).toBeNull()
    expect(screen.queryByRole('button', { name: /google/i })).toBeNull()
  })

  it('preserves the guest save query across signup and handles login safely', async () => {
    authService.login.mockRejectedValue(new Error('private backend detail'))
    render(<MemoryRouter initialEntries={['/login?saveGuest=1']}><Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<p>Cadastro</p>} />
    </Routes></MemoryRouter>)
    expect((await screen.findByRole('link', { name: /criar uma conta/i })).getAttribute('href')).toBe('/signup?saveGuest=1')
    fireEvent.change(screen.getByLabelText('Usuário'), { target: { value: 'visitor' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'invalid-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByText('private backend detail')).toBeNull()
  })

  it('creates an account with username credentials and returns to the app', async () => {
    const setSession = vi.fn()
    useAuthStore.setState({ setSession })
    authService.signup.mockResolvedValue({ access_token: 'opaque-token', user: { username: 'visitor', registration_source: 'public' } })
    render(<MemoryRouter initialEntries={['/signup?saveGuest=1']}><Routes>
      <Route path="/signup" element={<Login signup />} />
      <Route path="/new-transcription" element={<p>USAGI</p>} />
    </Routes></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('Usuário'), { target: { value: 'visitor' } })
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'visitor@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'long synthetic password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar conta' }))
    expect(await screen.findByText('USAGI')).toBeTruthy()
    expect(authService.signup).toHaveBeenCalledWith('visitor', 'visitor@example.test', 'long synthetic password')
    expect(setSession).toHaveBeenCalledWith(expect.objectContaining({ registration_source: 'public' }), 'opaque-token')
  })

  it('announces an in-progress login and disables repeat submission', async () => {
    let finishLogin
    authService.login.mockReturnValue(new Promise((resolve) => { finishLogin = resolve }))
    render(<MemoryRouter><Login /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Usuário'), { target: { value: 'visitor' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    const submit = await screen.findByRole('button', { name: 'Carregando...' })
    expect(submit.disabled).toBe(true)
    expect(submit.getAttribute('aria-busy')).toBe('true')
    finishLogin({ access_token: 'opaque-token', user: { username: 'visitor' } })
  })

  it('shows Google only when public Firebase config matches backend config and logs in', async () => {
    const setFirebaseSession = vi.fn()
    useAuthStore.setState({ setFirebaseSession })
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'public-project', local_signup_enabled: false })
    firebaseAuth.isConfigured.mockReturnValue(true)
    firebaseAuth.projectId.mockReturnValue('public-project')
    firebaseAuth.signInWithGoogle.mockResolvedValue('id-token')
    authService.firebaseLogin.mockResolvedValue({ user: { id: 7, auth_provider: 'firebase' } })
    render(<MemoryRouter initialEntries={['/login?returnTo=%2Fhistory&saveGuest=1']}><Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/history" element={<p>History</p>} />
    </Routes></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Continuar com Google' }))
    expect(await screen.findByText('History')).toBeTruthy()
    expect(authService.firebaseLogin).toHaveBeenCalledWith('id-token')
    expect(setFirebaseSession).toHaveBeenCalledWith({ id: 7, auth_provider: 'firebase' })
  })

  it('hides Google on a project mismatch and avoids exposing auth errors', async () => {
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'backend-project', local_signup_enabled: true })
    firebaseAuth.isConfigured.mockReturnValue(true)
    firebaseAuth.projectId.mockReturnValue('different-project')
    render(<MemoryRouter><Login /></MemoryRouter>)
    await waitFor(() => expect(authService.getConfig).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: 'Continuar com Google' })).toBeNull()
  })

  it('cleans up Firebase state after backend login failure with a fixed message', async () => {
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'public-project', local_signup_enabled: true })
    firebaseAuth.isConfigured.mockReturnValue(true)
    firebaseAuth.projectId.mockReturnValue('public-project')
    firebaseAuth.signInWithGoogle.mockResolvedValue('id-token')
    authService.firebaseLogin.mockRejectedValue(new Error('sensitive backend detail'))
    render(<MemoryRouter><Login /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Continuar com Google' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Não foi possível entrar com Google. Tente novamente.')
    expect(screen.queryByText('sensitive backend detail')).toBeNull()
    expect(firebaseAuth.signOut).toHaveBeenCalled()
  })

  it('hides local signup until config is available and when backend disables it', async () => {
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'other', local_signup_enabled: false })
    render(<MemoryRouter><Login /></MemoryRouter>)
    await waitFor(() => expect(screen.queryByRole('link', { name: /criar uma conta/i })).toBeNull())
    expect(screen.queryByRole('link', { name: /criar uma conta/i })).toBeNull()
  })
})
