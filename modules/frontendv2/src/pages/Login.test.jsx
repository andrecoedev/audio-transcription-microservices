import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Login from './Login'
import { authService } from '../services/authService'
import { useAuthStore } from '../stores/authStore'
import { firebaseAuth } from '../services/firebaseAuth'

vi.mock('../services/authService', () => ({ authService: { signup: vi.fn(), login: vi.fn(), getConfig: vi.fn(), firebaseLogin: vi.fn() } }))
vi.mock('../services/firebaseAuth', () => ({ firebaseAuth: {
  isConfigured: vi.fn(), projectId: vi.fn(), signInWithGoogle: vi.fn(), signOut: vi.fn(),
  signInWithEmail: vi.fn(), createWithEmail: vi.fn(), resendVerification: vi.fn(),
  refreshVerification: vi.fn(), resetPassword: vi.fn(), getEmailVerificationState: vi.fn(),
} }))

beforeEach(() => {
  vi.resetAllMocks()
  authService.getConfig.mockResolvedValue({ firebase_enabled: false, firebase_project_id: null, firebase_password_enabled: false, local_signup_enabled: true })
  firebaseAuth.isConfigured.mockReturnValue(false)
  firebaseAuth.projectId.mockReturnValue(null)
  firebaseAuth.getEmailVerificationState.mockResolvedValue(null)
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

  it('uses Firebase email login as the primary flow only when both configs match and returns to the requested page', async () => {
    const setFirebaseSession = vi.fn()
    useAuthStore.setState({ setFirebaseSession })
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'public-project', firebase_password_enabled: true, local_signup_enabled: true })
    firebaseAuth.isConfigured.mockReturnValue(true)
    firebaseAuth.projectId.mockReturnValue('public-project')
    firebaseAuth.signInWithEmail.mockResolvedValue({ verified: true, token: 'email-id-token' })
    authService.firebaseLogin.mockResolvedValue({ user: { id: 42, auth_provider: 'firebase' } })
    render(<MemoryRouter initialEntries={['/login?returnTo=%2Fhistory%3Fpage%3D2&saveGuest=1']}><Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/history" element={<p>History</p>} />
    </Routes></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'user@example.test' } })
    const passwordInput = screen.getByLabelText('Senha')
    fireEvent.change(passwordInput, { target: { value: 'private-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar com e-mail' }))
    expect(await screen.findByText('History')).toBeTruthy()
    expect(firebaseAuth.signInWithEmail).toHaveBeenCalledWith('user@example.test', 'private-password')
    expect(authService.firebaseLogin).toHaveBeenCalledWith('email-id-token')
    expect(setFirebaseSession).toHaveBeenCalledWith({ id: 42, auth_provider: 'firebase' })
    expect(passwordInput.value).toBe('')
    expect(screen.queryByLabelText('Usuário')).toBeNull()
  })

  it('keeps unverified email registration pending without exchanging a token or setting a session', async () => {
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'public-project', firebase_password_enabled: true, local_signup_enabled: false })
    firebaseAuth.isConfigured.mockReturnValue(true)
    firebaseAuth.projectId.mockReturnValue('public-project')
    firebaseAuth.createWithEmail.mockResolvedValue({ verified: false, token: null })
    render(<MemoryRouter initialEntries={['/signup?returnTo=%2Fhistory&saveGuest=1']}><Routes>
      <Route path="/signup" element={<Login signup />} />
      <Route path="/history" element={<p>History</p>} />
    </Routes></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'new@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'a long password 123' } })
    fireEvent.change(screen.getByLabelText('Confirme a senha'), { target: { value: 'a long password 123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar conta com e-mail' }))
    expect(await screen.findByRole('heading', { name: 'Confirme seu e-mail' })).toBeTruthy()
    expect(screen.getByText('Confirme new@example.test pelo link enviado para acessar sua conta.')).toBeTruthy()
    expect(firebaseAuth.createWithEmail).toHaveBeenCalledWith('new@example.test', 'a long password 123')
    expect(authService.firebaseLogin).not.toHaveBeenCalled()
    expect(useAuthStore.getState().setFirebaseSession).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /Enviar outro link em 60s/ }).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar e voltar' }))
    expect(await screen.findByLabelText('Senha')).toBeTruthy()
    expect(screen.getByLabelText('Senha').value).toBe('')
    expect(firebaseAuth.signOut).toHaveBeenCalledOnce()
  })

  it('exchanges a fresh token only after email verification is confirmed', async () => {
    const setFirebaseSession = vi.fn()
    useAuthStore.setState({ setFirebaseSession })
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'public-project', firebase_password_enabled: true })
    firebaseAuth.isConfigured.mockReturnValue(true)
    firebaseAuth.projectId.mockReturnValue('public-project')
    firebaseAuth.createWithEmail.mockResolvedValue({ verified: false, token: null })
    firebaseAuth.refreshVerification.mockResolvedValue({ verified: true, token: 'fresh-id-token' })
    authService.firebaseLogin.mockResolvedValue({ user: { id: 7 } })
    render(<MemoryRouter initialEntries={['/signup?returnTo=%2Fhistory']}><Routes>
      <Route path="/signup" element={<Login signup />} />
      <Route path="/history" element={<p>History</p>} />
    </Routes></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'new@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'a long password 123' } })
    fireEvent.change(screen.getByLabelText('Confirme a senha'), { target: { value: 'a long password 123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar conta com e-mail' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Já confirmei meu e-mail' }))
    expect(await screen.findByText('History')).toBeTruthy()
    expect(firebaseAuth.refreshVerification).toHaveBeenCalledOnce()
    expect(authService.firebaseLogin).toHaveBeenCalledWith('fresh-id-token')
    expect(setFirebaseSession).toHaveBeenCalledWith({ id: 7 })
  })

  it('restores an unverified Firebase session after reload without admitting it', async () => {
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'public-project', firebase_password_enabled: true })
    firebaseAuth.isConfigured.mockReturnValue(true)
    firebaseAuth.projectId.mockReturnValue('public-project')
    firebaseAuth.getEmailVerificationState.mockResolvedValue({ verified: false, token: null })
    render(<MemoryRouter><Login /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Confirme seu e-mail' })).toBeTruthy()
    expect(firebaseAuth.getEmailVerificationState).toHaveBeenCalledOnce()
    expect(authService.firebaseLogin).not.toHaveBeenCalled()
    expect(useAuthStore.getState().setFirebaseSession).not.toHaveBeenCalled()
  })

  it('validates signup password confirmation and exposes a generic recovery success', async () => {
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'public-project', firebase_password_enabled: true })
    firebaseAuth.isConfigured.mockReturnValue(true)
    firebaseAuth.projectId.mockReturnValue('public-project')
    render(<MemoryRouter initialEntries={['/signup?returnTo=%2Fhistory&saveGuest=1']}><Routes>
      <Route path="/signup" element={<Login signup />} />
      <Route path="/login" element={<Login />} />
    </Routes></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'person@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'a long password 123' } })
    fireEvent.change(screen.getByLabelText('Confirme a senha'), { target: { value: 'different password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar conta com e-mail' }))
    expect((await screen.findByRole('alert')).textContent).toContain('As senhas não coincidem.')
    expect(firebaseAuth.createWithEmail).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Entrar com usuário e senha (conta local)' }))
    expect(await screen.findByLabelText('Usuário')).toBeTruthy()
  })

  it('uses a generic recovery success message and keeps auth return query intact', async () => {
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'public-project', firebase_password_enabled: true })
    firebaseAuth.isConfigured.mockReturnValue(true)
    firebaseAuth.projectId.mockReturnValue('public-project')
    firebaseAuth.resetPassword.mockResolvedValue(undefined)
    render(<MemoryRouter initialEntries={['/login?returnTo=%2Fhistory&saveGuest=1']}><Routes>
      <Route path="/login" element={<Login />} />
    </Routes></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Esqueci minha senha' }))
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'unknown@example.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar instruções' }))
    expect((await screen.findByRole('status')).textContent).toContain('Se houver uma conta para este e-mail')
    expect(firebaseAuth.resetPassword).toHaveBeenCalledWith('unknown@example.test')
  })

  it('shows the local account migration path after a Firebase backend conflict', async () => {
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'public-project', firebase_password_enabled: true, local_signup_enabled: true })
    firebaseAuth.isConfigured.mockReturnValue(true)
    firebaseAuth.projectId.mockReturnValue('public-project')
    firebaseAuth.signInWithEmail.mockResolvedValue({ verified: true, token: 'email-id-token' })
    authService.firebaseLogin.mockRejectedValue({ status: 409, message: 'private backend detail' })
    render(<MemoryRouter><Login /></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'local@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'private-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar com e-mail' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Entre com seu usuário e senha')
    expect(screen.getByRole('alert').textContent).toContain('migre a conta para o acesso por e-mail')
    expect(screen.queryByText('private backend detail')).toBeNull()
    expect(screen.getByRole('button', { name: 'Entrar com usuário e senha (conta local)' })).toBeTruthy()
    expect(firebaseAuth.signOut).toHaveBeenCalled()
  })
})
