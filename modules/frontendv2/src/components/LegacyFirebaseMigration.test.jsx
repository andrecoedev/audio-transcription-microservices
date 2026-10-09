import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import LegacyFirebaseMigration from './LegacyFirebaseMigration'
import { authService } from '../services/authService'
import { firebaseAuth } from '../services/firebaseAuth'
import { useAuthStore } from '../stores/authStore'

vi.mock('../services/authService', () => ({ authService: { getConfig: vi.fn(), linkGoogle: vi.fn(), firebaseLogin: vi.fn() } }))
vi.mock('../services/firebaseAuth', () => ({
  firebaseAuth: {
    isConfigured: vi.fn(), projectId: vi.fn(), createWithEmail: vi.fn(), signInWithEmail: vi.fn(),
    getEmailVerificationState: vi.fn(), refreshVerification: vi.fn(), resendVerification: vi.fn(), signOut: vi.fn(),
  },
}))

const localUser = { id: 23, username: 'local-user', firebase_connected: false, google_connected: false }
const renderMigration = () => render(<LegacyFirebaseMigration />)

beforeEach(() => {
  vi.resetAllMocks()
  authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_password_enabled: true, firebase_project_id: 'project-a' })
  firebaseAuth.isConfigured.mockReturnValue(true)
  firebaseAuth.projectId.mockReturnValue('project-a')
  firebaseAuth.signOut.mockResolvedValue(undefined)
  firebaseAuth.getEmailVerificationState.mockResolvedValue(null)
  useAuthStore.setState({
    user: localUser, authProvider: 'local', isAuthenticated: true,
    setFirebaseSession: vi.fn(),
  })
})

afterEach(() => cleanup())

describe('LegacyFirebaseMigration', () => {
  it('requires the explicit feature flag and matching configured Firebase project', async () => {
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_password_enabled: false, firebase_project_id: 'project-a' })
    const { unmount } = renderMigration()
    await waitFor(() => expect(authService.getConfig).toHaveBeenCalledOnce())
    expect(screen.queryByRole('heading', { name: 'Conectar acesso por e-mail' })).toBeNull()

    unmount()
    authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_password_enabled: true, firebase_project_id: 'other-project' })
    renderMigration()
    await waitFor(() => expect(authService.getConfig).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('heading', { name: 'Conectar acesso por e-mail' })).toBeNull()
  })

  it('does not show migration for guest or Firebase sessions', async () => {
    useAuthStore.setState({ isAuthenticated: false })
    const { rerender } = renderMigration()
    await waitFor(() => expect(authService.getConfig).toHaveBeenCalledOnce())
    expect(screen.queryByRole('heading', { name: 'Conectar acesso por e-mail' })).toBeNull()

    useAuthStore.setState({ user: localUser, isAuthenticated: true, authProvider: 'firebase' })
    rerender(<LegacyFirebaseMigration />)
    expect(screen.queryByRole('heading', { name: 'Conectar acesso por e-mail' })).toBeNull()
  })

  it('creates a pending Firebase identity, verifies it, then connects it to the same internal account', async () => {
    const setFirebaseSession = vi.fn()
    useAuthStore.setState({ setFirebaseSession })
    firebaseAuth.createWithEmail.mockResolvedValue({ verified: false, token: null })
    firebaseAuth.refreshVerification.mockResolvedValue({ verified: true, token: 'verified-id-token' })
    authService.linkGoogle.mockImplementation(async (_token, submittedPassword) => {
      expect(submittedPassword).toBe('legacy-password')
      return { user: { ...localUser, firebase_connected: true } }
    })
    renderMigration()

    fireEvent.click(await screen.findByLabelText('Criar acesso por e-mail'))
    fireEvent.change(screen.getByLabelText('E-mail do acesso'), { target: { value: 'new@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha do acesso por e-mail'), { target: { value: 'target-password' } })
    fireEvent.change(screen.getByLabelText('Confirmar senha'), { target: { value: 'target-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar acesso por e-mail' }))

    expect(await screen.findByText(/Confirme o endereço pelo link/)).toBeTruthy()
    expect(firebaseAuth.createWithEmail).toHaveBeenCalledWith('new@example.test', 'target-password')
    expect(screen.queryByLabelText('Senha do acesso por e-mail')).toBeNull()
    expect(screen.queryByLabelText('Confirmar senha')).toBeNull()
    expect(screen.getByRole('button', { name: 'Reenviar e-mail (60s)' }).disabled).toBe(true)
    expect(authService.linkGoogle).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Já confirmei meu e-mail' }))
    fireEvent.change(await screen.findByLabelText('Senha USAGI atual'), { target: { value: 'legacy-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Conectar à conta atual' }))

    await waitFor(() => expect(setFirebaseSession).toHaveBeenCalledWith(expect.objectContaining({ id: 23 })))
    expect(authService.linkGoogle).toHaveBeenCalledWith('verified-id-token', 'legacy-password')
    expect(screen.getByRole('status').textContent).toContain('Seus dados permanecem nesta conta')
    expect(firebaseAuth.signInWithEmail).not.toHaveBeenCalled()
  })

  it('uses an existing verified Firebase account without calling Firebase login exchange', async () => {
    firebaseAuth.signInWithEmail.mockResolvedValue({ verified: true, token: 'existing-id-token' })
    authService.linkGoogle.mockResolvedValue({ user: { ...localUser } })
    renderMigration()
    fireEvent.change(await screen.findByLabelText('E-mail do acesso'), { target: { value: 'existing@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha do acesso por e-mail'), { target: { value: 'target-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }))

    expect(await screen.findByLabelText('Senha USAGI atual')).toBeTruthy()
    expect(firebaseAuth.signInWithEmail).toHaveBeenCalledWith('existing@example.test', 'target-password')
    expect(authService.firebaseLogin).not.toHaveBeenCalled()
  })

  it('keeps the local session and handles backend conflicts without assigning another identity', async () => {
    const setFirebaseSession = vi.fn()
    useAuthStore.setState({ setFirebaseSession })
    firebaseAuth.signInWithEmail.mockResolvedValue({ verified: true, token: 'existing-id-token' })
    authService.linkGoogle.mockResolvedValue({ user: { ...localUser, id: 99 } })
    renderMigration()
    fireEvent.change(await screen.findByLabelText('E-mail do acesso'), { target: { value: 'existing@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha do acesso por e-mail'), { target: { value: 'target-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    fireEvent.change(await screen.findByLabelText('Senha USAGI atual'), { target: { value: 'legacy-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Conectar à conta atual' }))

    expect((await screen.findByRole('alert')).textContent).toContain('não pode ser conectado')
    expect(setFirebaseSession).not.toHaveBeenCalled()
    expect(firebaseAuth.signOut).toHaveBeenCalledOnce()
    expect(useAuthStore.getState().authProvider).toBe('local')
  })

  it('shows already-connected status without attempting automatic account matching', async () => {
    useAuthStore.setState({ user: { ...localUser, firebase_connected: true } })
    renderMigration()
    expect((await screen.findByRole('status')).textContent).toContain('Acesso conectado')
    expect(screen.queryByLabelText('E-mail do acesso')).toBeNull()
  })

  it('restores a pending verification from Firebase without storing target credentials', async () => {
    firebaseAuth.getEmailVerificationState.mockResolvedValue({ verified: false, token: null })
    firebaseAuth.refreshVerification.mockResolvedValue({ verified: true, token: 'restored-id-token' })
    renderMigration()

    expect(await screen.findByText(/Confirme o endereço pelo link/)).toBeTruthy()
    expect(screen.queryByLabelText('Senha do acesso por e-mail')).toBeNull()
    expect(firebaseAuth.createWithEmail).not.toHaveBeenCalled()
    expect(firebaseAuth.signInWithEmail).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Já confirmei meu e-mail' }))
    expect(await screen.findByLabelText('Senha USAGI atual')).toBeTruthy()
  })

  it('reports failed Firebase cleanup while preserving the local session', async () => {
    firebaseAuth.signInWithEmail.mockResolvedValue({ verified: true, token: 'existing-id-token' })
    firebaseAuth.signOut.mockRejectedValue(new Error('private SDK error'))
    renderMigration()
    fireEvent.change(await screen.findByLabelText('E-mail do acesso'), { target: { value: 'existing@example.test' } })
    fireEvent.change(screen.getByLabelText('Senha do acesso por e-mail'), { target: { value: 'target-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar' }))

    expect((await screen.findByRole('alert')).textContent).toContain('ainda pode estar ativo')
    expect(screen.queryByText('private SDK error')).toBeNull()
    expect(useAuthStore.getState().authProvider).toBe('local')
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
  })
})
