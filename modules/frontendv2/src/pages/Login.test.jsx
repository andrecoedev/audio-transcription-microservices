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
  refreshVerification: vi.fn(), resetPassword: vi.fn(), getEmailVerificationState: vi.fn(), validatePassword: vi.fn(),
} }))

const enabledConfig = {
  firebase_enabled: true,
  firebase_project_id: 'public-project',
  firebase_password_enabled: true,
}

function enableFirebase(config = enabledConfig) {
  authService.getConfig.mockResolvedValue(config)
  firebaseAuth.isConfigured.mockReturnValue(true)
  firebaseAuth.projectId.mockReturnValue('public-project')
}

function passwordStatus(password, options = { minPasswordLength: 8 }) {
  const meetsMinPasswordLength = password.length >= (options.minPasswordLength ?? 0)
  const meetsMaxPasswordLength = password.length <= (options.maxPasswordLength ?? Infinity)
  const criteria = {
    containsUppercaseLetter: /[A-Z]/.test(password),
    containsLowercaseLetter: /[a-z]/.test(password),
    containsNumericCharacter: /[0-9]/.test(password),
    containsNonAlphanumericCharacter: /[^A-Za-z0-9]/.test(password),
  }
  const isValid = meetsMinPasswordLength && meetsMaxPasswordLength
    && Object.entries(criteria).every(([criterion, met]) => options[criterion] !== true || met)
  return {
    isValid,
    meetsMinPasswordLength,
    meetsMaxPasswordLength,
    ...criteria,
    passwordPolicy: { customStrengthOptions: options },
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  authService.getConfig.mockResolvedValue({ firebase_enabled: false, firebase_project_id: null, firebase_password_enabled: false, local_signup_enabled: true })
  firebaseAuth.isConfigured.mockReturnValue(false)
  firebaseAuth.projectId.mockReturnValue(null)
  firebaseAuth.getEmailVerificationState.mockResolvedValue(null)
  firebaseAuth.validatePassword.mockImplementation(async (password) => passwordStatus(password))
  useAuthStore.setState({ setSession: vi.fn(), setFirebaseSession: vi.fn() })
})
afterEach(cleanup)

describe('Login', () => {
  it('uses public email login without username or local account options', async () => {
    render(<MemoryRouter><Login /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Salve seu trabalho' })).toBeTruthy()
    expect(await screen.findByLabelText('E-mail')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Entrar' }).disabled).toBe(true)
    expect(screen.queryByLabelText('Usuário')).toBeNull()
    expect(screen.queryByText(/conta local|Firebase|PostgreSQL|UID/i)).toBeNull()
    expect(screen.getByRole('link', { name: 'Continuar sem conta' })).toBeTruthy()
    expect(screen.queryByRole('complementary')).toBeNull()
  })

  it('keeps public signup on Firebase email even when reached from /signup?legacy=1', async () => {
    render(<MemoryRouter initialEntries={['/signup?legacy=1&saveGuest=1']}><Routes>
      <Route path="/signup" element={<Login signup />} />
    </Routes></MemoryRouter>)
    expect(await screen.findByLabelText('E-mail')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(true)
    expect(screen.getByLabelText('Confirmar senha')).toBeTruthy()
    expect(screen.queryByLabelText('Usuário')).toBeNull()
    expect(authService.signup).not.toHaveBeenCalled()
  })

  it('shows legacy username login only on the explicit /login?legacy=1 route', async () => {
    authService.login.mockRejectedValue(new Error('private backend detail'))
    render(<MemoryRouter initialEntries={['/login?legacy=1']}><Routes>
      <Route path="/login" element={<Login />} />
    </Routes></MemoryRouter>)
    expect(await screen.findByLabelText('Usuário')).toBeTruthy()
    expect(screen.getByLabelText('Usuário').getAttribute('autocomplete')).toBe('username')
    expect(screen.getByLabelText('Senha').getAttribute('autocomplete')).toBe('current-password')
    expect(screen.queryByLabelText('E-mail')).toBeNull()
    expect(screen.queryByRole('link', { name: /criar uma conta/i })).toBeNull()
    fireEvent.change(screen.getByLabelText('Usuário'), { target: { value: 'visitor' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'synthetic-pass' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByText('private backend detail')).toBeNull()
  })

  it('preserves guest save query across public signup navigation', async () => {
    render(<MemoryRouter initialEntries={['/login?saveGuest=1']}><Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<p>Cadastro</p>} />
    </Routes></MemoryRouter>)
    expect((await screen.findByRole('link', { name: /criar uma conta/i })).getAttribute('href')).toBe('/signup?saveGuest=1')
    expect(authService.login).not.toHaveBeenCalled()
  })

  it('shows Google only when public Firebase config matches backend config and logs in', async () => {
    const setFirebaseSession = vi.fn()
    useAuthStore.setState({ setFirebaseSession })
    enableFirebase({ ...enabledConfig, local_signup_enabled: false })
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

  it('hides Google on project mismatch and keeps public email action disabled without configured email auth', async () => {
    authService.getConfig.mockResolvedValue({ ...enabledConfig, firebase_project_id: 'backend-project' })
    firebaseAuth.isConfigured.mockReturnValue(true)
    firebaseAuth.projectId.mockReturnValue('different-project')
    render(<MemoryRouter><Login /></MemoryRouter>)
    await waitFor(() => expect(authService.getConfig).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: 'Continuar com Google' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Entrar' }).disabled).toBe(true)
    expect(screen.queryByLabelText('Usuário')).toBeNull()
  })

  it('logs in with Firebase email and returns to requested destination', async () => {
    const setFirebaseSession = vi.fn()
    useAuthStore.setState({ setFirebaseSession })
    enableFirebase()
    firebaseAuth.signInWithEmail.mockResolvedValue({ verified: true, token: 'email-id-token' })
    authService.firebaseLogin.mockResolvedValue({ user: { id: 42, auth_provider: 'firebase' } })
    render(<MemoryRouter initialEntries={['/login?returnTo=%2Fhistory%3Fpage%3D2&saveGuest=1']}><Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/history" element={<p>History</p>} />
    </Routes></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'user@example.test' } })
    const passwordInput = screen.getByLabelText('Senha')
    fireEvent.change(passwordInput, { target: { value: 'synthetic-pass' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText('History')).toBeTruthy()
    expect(firebaseAuth.signInWithEmail).toHaveBeenCalledWith('user@example.test', 'synthetic-pass')
    expect(authService.firebaseLogin).toHaveBeenCalledWith('email-id-token')
    expect(setFirebaseSession).toHaveBeenCalledWith({ id: 42, auth_provider: 'firebase' })
    expect(passwordInput.value).toBe('')
  })

  it('accepts a valid eight character Firebase password and shows optional policy criteria only when configured', async () => {
    enableFirebase()
    firebaseAuth.validatePassword.mockImplementation(async (password) => passwordStatus(password, {
      minPasswordLength: 8,
      containsUppercaseLetter: true,
    }))
    firebaseAuth.createWithEmail.mockResolvedValue({ verified: false, token: null })
    render(<MemoryRouter initialEntries={['/signup']}><Routes>
      <Route path="/signup" element={<Login signup />} />
    </Routes></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'new@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'Eight888' } })
    fireEvent.change(screen.getByLabelText('Confirmar senha'), { target: { value: 'Eight888' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(false))
    const checklist = screen.getByRole('list', { name: 'Requisitos da senha' })
    expect(checklist.textContent).toContain('Pelo menos 8 caracteres')
    expect(checklist.textContent).toContain('Contém letra maiúscula')
    expect(checklist.textContent).not.toContain('Contém número')
    expect(checklist.textContent).not.toContain('caractere especial')
    fireEvent.click(screen.getByRole('button', { name: 'Criar conta' }))
    expect(firebaseAuth.createWithEmail).toHaveBeenCalledWith('new@example.test', 'Eight888')
    expect(await screen.findByRole('heading', { name: 'Confirme seu e-mail' })).toBeTruthy()
  })

  it('blocks signup when a configured numeric criterion is missing, then enables it when met', async () => {
    enableFirebase()
    firebaseAuth.validatePassword.mockImplementation(async (password) => passwordStatus(password, {
      minPasswordLength: 8,
      containsNumericCharacter: true,
    }))
    render(<MemoryRouter><Login signup /></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'new@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'NoDigits' } })
    fireEvent.change(screen.getByLabelText('Confirmar senha'), { target: { value: 'NoDigits' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(true))
    expect(screen.getByRole('list', { name: 'Requisitos da senha' }).querySelectorAll('li')[1].textContent).toContain('Pendente: Contém número')
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'HasDigit8' } })
    fireEvent.change(screen.getByLabelText('Confirmar senha'), { target: { value: 'HasDigit8' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(false))
    expect(screen.getByRole('list', { name: 'Requisitos da senha' }).querySelectorAll('li')[1].textContent).toContain('Atendido: Contém número')
  })

  it('keeps Google failures generic and clears a Firebase session after backend failure', async () => {
    enableFirebase()
    firebaseAuth.signInWithGoogle.mockResolvedValue('id-token')
    authService.firebaseLogin.mockRejectedValue(new Error('private backend detail'))
    render(<MemoryRouter><Login /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Continuar com Google' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Não foi possível entrar com Google')
    expect(screen.queryByText('private backend detail')).toBeNull()
    expect(firebaseAuth.signOut).toHaveBeenCalledOnce()
  })

  it('reports failed Firebase cleanup without exposing cleanup details', async () => {
    enableFirebase()
    firebaseAuth.signInWithEmail.mockRejectedValue({ code: 'auth/invalid-credential' })
    firebaseAuth.signOut.mockRejectedValue(new Error('private cleanup detail'))
    render(<MemoryRouter><Login /></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'user@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'synthetic-pass' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('encerrar a sessão pendente')
    expect(alert.textContent).not.toContain('private cleanup detail')
  })

  it.each(['auth/invalid-credential', 'auth/wrong-password', 'auth/user-not-found'])(
    'uses the same neutral email login error for %s', async (code) => {
      enableFirebase()
      firebaseAuth.signInWithEmail.mockRejectedValue({ code })
      render(<MemoryRouter><Login /></MemoryRouter>)
      fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'user@example.test' } })
      fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'synthetic-pass' } })
      fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
      expect((await screen.findByRole('alert')).textContent).toBe('E-mail ou senha inválidos.')
      expect(screen.queryByRole('link', { name: 'Atualizar método de acesso' })).toBeNull()
    },
  )

  it('shows legacy migration only after a backend account conflict', async () => {
    enableFirebase()
    firebaseAuth.signInWithEmail.mockResolvedValue({ verified: true, token: 'id-token' })
    authService.firebaseLogin.mockRejectedValue({ status: 409, message: 'private backend detail' })
    render(<MemoryRouter initialEntries={['/login?saveGuest=1']}><Routes>
      <Route path="/login" element={<Login />} />
    </Routes></MemoryRouter>)
    expect(screen.queryByRole('link', { name: 'Atualizar método de acesso' })).toBeNull()
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'local@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'synthetic-pass' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect((await screen.findByRole('alert')).textContent).toContain('atualizado')
    expect(screen.queryByText('private backend detail')).toBeNull()
    const migrationLink = screen.getByRole('link', { name: 'Atualizar método de acesso' })
    expect(migrationLink.getAttribute('href')).toContain('/login?legacy=1')
    expect(screen.queryByLabelText('Usuário')).toBeNull()
    expect(authService.login).not.toHaveBeenCalled()
    expect(firebaseAuth.signOut).toHaveBeenCalledOnce()
  })

  it('announces pending email login and disables repeat submission', async () => {
    enableFirebase()
    let finishLogin
    firebaseAuth.signInWithEmail.mockReturnValue(new Promise((resolve) => { finishLogin = resolve }))
    render(<MemoryRouter><Login /></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'user@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'synthetic-pass' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    const submit = (await screen.findAllByRole('button', { name: 'Carregando...' }))
      .find((button) => button.type === 'submit')
    expect(submit.disabled).toBe(true)
    expect(submit.getAttribute('aria-busy')).toBe('true')
    fireEvent.click(submit)
    expect(firebaseAuth.signInWithEmail).toHaveBeenCalledOnce()
    finishLogin({ verified: false, token: null })
  })

  it('updates checklist states while typing and keeps signup confirmation required and matched', async () => {
    enableFirebase()
    firebaseAuth.createWithEmail.mockResolvedValue({ verified: false, token: null })
    render(<MemoryRouter><Login signup /></MemoryRouter>)
    const email = await screen.findByLabelText('E-mail')
    const password = screen.getByLabelText('Senha')
    const confirmation = screen.getByLabelText('Confirmar senha')
    expect(email.required).toBe(true)
    expect(password.required).toBe(true)
    expect(confirmation.required).toBe(true)
    const checklist = screen.getByRole('list', { name: 'Requisitos da senha' })
    fireEvent.change(email, { target: { value: 'person@example.test' } })
    fireEvent.change(password, { target: { value: 'short' } })
    fireEvent.change(confirmation, { target: { value: 'short' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(true))
    expect(checklist.querySelectorAll('li')[0].textContent).toContain('Pendente: Pelo menos 8 caracteres')
    expect(checklist.querySelectorAll('li')[1].textContent).toContain('Atendido: As senhas coincidem')
    fireEvent.change(password, { target: { value: 'validpass' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(true))
    expect(screen.getByRole('list', { name: 'Requisitos da senha' }).querySelectorAll('li')[1].textContent).toContain('Pendente: As senhas coincidem')
    fireEvent.change(confirmation, { target: { value: 'validpass' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(false))
    expect(screen.getByRole('list', { name: 'Requisitos da senha' }).querySelectorAll('li')[0].textContent).toContain('Atendido: Pelo menos 8 caracteres')
    expect(screen.getByRole('list', { name: 'Requisitos da senha' }).querySelectorAll('li')[1].textContent).toContain('Atendido: As senhas coincidem')
  })

  it('blocks invalid policy, policy lookup failures, and stale validation results', async () => {
    enableFirebase()
    let resolveOld
    firebaseAuth.validatePassword.mockImplementation((password) => {
      if (password === 'old-valid-password') return new Promise((resolve) => { resolveOld = resolve })
      if (password === 'validpass') return Promise.resolve(passwordStatus(password))
      return Promise.resolve(passwordStatus(password))
    })
    render(<MemoryRouter><Login signup /></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('Senha'), { target: { value: 'invalid' } })
    fireEvent.change(screen.getByLabelText('Confirmar senha'), { target: { value: 'invalid' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(true))
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'old-valid-password' } })
    fireEvent.change(screen.getByLabelText('Confirmar senha'), { target: { value: 'validpass' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'validpass' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(false))
    resolveOld(passwordStatus('old-valid-password'))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(false))

    firebaseAuth.validatePassword.mockRejectedValue(new Error('offline'))
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'anotherpass' } })
    fireEvent.change(screen.getByLabelText('Confirmar senha'), { target: { value: 'anotherpass' } })
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(true)
  })

  it('keeps unverified email registration pending without admitting a session', async () => {
    enableFirebase()
    firebaseAuth.createWithEmail.mockResolvedValue({ verified: false, token: null })
    render(<MemoryRouter initialEntries={['/signup']}><Routes>
      <Route path="/signup" element={<Login signup />} />
    </Routes></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'new@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'validpass' } })
    fireEvent.change(screen.getByLabelText('Confirmar senha'), { target: { value: 'validpass' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: 'Criar conta' }))
    expect(await screen.findByRole('heading', { name: 'Confirme seu e-mail' })).toBeTruthy()
    expect(firebaseAuth.createWithEmail).toHaveBeenCalledWith('new@example.test', 'validpass')
    expect(authService.firebaseLogin).not.toHaveBeenCalled()
    expect(useAuthStore.getState().setFirebaseSession).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /Enviar outro link em 60s/ }).disabled).toBe(true)
  })

  it('exchanges a fresh token only after email verification is confirmed', async () => {
    const setFirebaseSession = vi.fn()
    useAuthStore.setState({ setFirebaseSession })
    enableFirebase()
    firebaseAuth.createWithEmail.mockResolvedValue({ verified: false, token: null })
    firebaseAuth.refreshVerification.mockResolvedValue({ verified: true, token: 'fresh-id-token' })
    authService.firebaseLogin.mockResolvedValue({ user: { id: 7 } })
    render(<MemoryRouter initialEntries={['/signup?returnTo=%2Fhistory']}><Routes>
      <Route path="/signup" element={<Login signup />} />
      <Route path="/history" element={<p>History</p>} />
    </Routes></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'new@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'validpass' } })
    fireEvent.change(screen.getByLabelText('Confirmar senha'), { target: { value: 'validpass' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Criar conta' }).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: 'Criar conta' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Já confirmei meu e-mail' }))
    expect(await screen.findByText('History')).toBeTruthy()
    expect(authService.firebaseLogin).toHaveBeenCalledWith('fresh-id-token')
    expect(setFirebaseSession).toHaveBeenCalledWith({ id: 7 })
  })

  it('restores an unverified Firebase session after reload without admitting it', async () => {
    enableFirebase()
    firebaseAuth.getEmailVerificationState.mockResolvedValue({ verified: false, token: null })
    render(<MemoryRouter><Login /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Confirme seu e-mail' })).toBeTruthy()
    expect(authService.firebaseLogin).not.toHaveBeenCalled()
    expect(useAuthStore.getState().setFirebaseSession).not.toHaveBeenCalled()
  })

  it('does not claim to send verification mail during an unverified email login', async () => {
    enableFirebase()
    firebaseAuth.signInWithEmail.mockResolvedValue({ verified: false, token: null })
    render(<MemoryRouter><Login /></MemoryRouter>)
    fireEvent.change(await screen.findByLabelText('E-mail'), { target: { value: 'user@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'synthetic-pass' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    const notice = await screen.findByRole('status')
    expect(notice.textContent).toContain('Confirme o endereço pelo link de verificação')
    expect(notice.textContent).not.toContain('Enviamos')
    expect(firebaseAuth.resendVerification).not.toHaveBeenCalled()
    expect(authService.firebaseLogin).not.toHaveBeenCalled()
  })

  it('preserves generic password recovery', async () => {
    enableFirebase()
    firebaseAuth.resetPassword.mockResolvedValue(undefined)
    render(<MemoryRouter><Login /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Esqueci minha senha' }))
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'unknown@example.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar instruções' }))
    expect((await screen.findByRole('status')).textContent).toContain('Se houver uma conta para este e-mail')
    expect(firebaseAuth.resetPassword).toHaveBeenCalledWith('unknown@example.test')
  })
})
