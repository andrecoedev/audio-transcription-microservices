import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import GoogleAccountLink from './GoogleAccountLink'
import { authService } from '../services/authService'
import { firebaseAuth } from '../services/firebaseAuth'
import { useAuthStore } from '../stores/authStore'

vi.mock('../services/authService', () => ({ authService: { getConfig: vi.fn(), linkGoogle: vi.fn() } }))
vi.mock('../services/firebaseAuth', () => ({ firebaseAuth: { isConfigured: vi.fn(), projectId: vi.fn(), signInWithGoogle: vi.fn(), signOut: vi.fn() } }))

beforeEach(() => {
  vi.resetAllMocks()
  authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'project-a' })
  firebaseAuth.isConfigured.mockReturnValue(true)
  firebaseAuth.projectId.mockReturnValue('project-a')
  useAuthStore.setState({
    user: { id: 23, username: 'local-user', google_connected: false },
    authProvider: 'local',
    setFirebaseSession: vi.fn(),
  })
})
afterEach(cleanup)

describe('GoogleAccountLink', () => {
  it('links after password reauthentication and preserves the backend user identity', async () => {
    const setFirebaseSession = vi.fn()
    useAuthStore.setState({ setFirebaseSession })
    firebaseAuth.signInWithGoogle.mockResolvedValue('google-id-token')
    authService.linkGoogle.mockImplementation(async (_token, submittedPassword) => {
      expect(screen.getByLabelText('Senha USAGI').value).toBe('')
      expect(submittedPassword).toBe('private-password')
      return { user: { id: 23, username: 'local-user', google_connected: true } }
    })
    render(<GoogleAccountLink />)
    fireEvent.change(await screen.findByLabelText('Senha USAGI'), { target: { value: 'private-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Conectar Google' }))
    await waitFor(() => expect(setFirebaseSession).toHaveBeenCalledWith({ id: 23, username: 'local-user', google_connected: true }))
    expect(authService.linkGoogle).toHaveBeenCalledWith('google-id-token', 'private-password')
  })

  it('clears password and shows a fixed error when linking fails, signing out Google', async () => {
    firebaseAuth.signInWithGoogle.mockResolvedValue('temporary-google-token')
    authService.linkGoogle.mockRejectedValue(new Error('secret server response'))
    render(<GoogleAccountLink />)
    fireEvent.change(await screen.findByLabelText('Senha USAGI'), { target: { value: 'private-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Conectar Google' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Não foi possível conectar o Google. Confirme sua senha e tente novamente.')
    expect(screen.getByLabelText('Senha USAGI').value).toBe('')
    expect(screen.queryByText('secret server response')).toBeNull()
    expect(firebaseAuth.signOut).toHaveBeenCalled()
  })

  it('reports when Google cleanup after a failed link also fails', async () => {
    firebaseAuth.signInWithGoogle.mockResolvedValue('temporary-google-token')
    authService.linkGoogle.mockRejectedValue(new Error('private detail'))
    firebaseAuth.signOut.mockRejectedValue(new Error('cleanup detail'))
    render(<GoogleAccountLink />)
    fireEvent.change(await screen.findByLabelText('Senha USAGI'), { target: { value: 'private-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Conectar Google' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Não foi possível conectar o Google nem encerrar a sessão Google.')
    expect(screen.queryByText(/private detail|cleanup detail/)).toBeNull()
  })

  it.each([
    [{ user: { id: 23, google_connected: true }, authProvider: 'local' }],
    [{ user: { id: 23, google_connected: false }, authProvider: 'firebase' }],
  ])('shows connected status for an already connected account', async (state) => {
    useAuthStore.setState(state)
    render(<GoogleAccountLink />)
    expect((await screen.findByRole('status')).textContent).toContain('Google conectado')
    expect(screen.queryByRole('button', { name: 'Conectar Google' })).toBeNull()
  })

  it('hides linking when backend and public Firebase configuration do not match', async () => {
    firebaseAuth.projectId.mockReturnValue('other-project')
    render(<GoogleAccountLink />)
    await waitFor(() => expect(authService.getConfig).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: 'Conectar Google' })).toBeNull()
  })
})
