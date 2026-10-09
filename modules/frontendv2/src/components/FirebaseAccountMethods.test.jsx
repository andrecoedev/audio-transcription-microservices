import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import FirebaseAccountMethods from './FirebaseAccountMethods'
import { authService } from '../services/authService'
import { firebaseAuth } from '../services/firebaseAuth'

vi.mock('../services/authService', () => ({ authService: { getConfig: vi.fn() } }))
vi.mock('../services/firebaseAuth', () => ({
  firebaseAuth: {
    getAuthMethods: vi.fn(), isConfigured: vi.fn(), projectId: vi.fn(),
    resetPassword: vi.fn(), validatePassword: vi.fn(), linkPassword: vi.fn(),
    reauthenticatePassword: vi.fn(), linkGoogle: vi.fn(), getToken: vi.fn(),
  },
}))

const account = { id: 7, email: 'account@example.test' }
const enabledConfig = { firebase_enabled: true, firebase_project_id: 'project-test', firebase_password_enabled: true }

beforeEach(() => {
  vi.resetAllMocks()
  authService.getConfig.mockResolvedValue(enabledConfig)
  firebaseAuth.getAuthMethods.mockResolvedValue(['google.com'])
  firebaseAuth.isConfigured.mockReturnValue(true)
  firebaseAuth.projectId.mockReturnValue('project-test')
  firebaseAuth.validatePassword.mockResolvedValue({ isValid: true })
})
afterEach(cleanup)

it('sends password reset for the account email and gives the same generic confirmation', async () => {
  firebaseAuth.getAuthMethods.mockResolvedValue(['password'])
  render(<FirebaseAccountMethods account={account} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Redefinir senha' }))
  expect((await screen.findByRole('status')).textContent).toContain('Se este e-mail puder redefinir uma senha')
  expect(firebaseAuth.resetPassword).toHaveBeenCalledWith(account.email)
})

it('validates and links a password to the current Firebase user, then clears both fields', async () => {
  render(<FirebaseAccountMethods account={account} />)
  const password = await screen.findByLabelText('Nova senha')
  const confirmation = screen.getByLabelText('Confirmar nova senha')
  fireEvent.change(password, { target: { value: 'a-long-private-password' } })
  fireEvent.change(confirmation, { target: { value: 'a-long-private-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar senha' }))
  await waitFor(() => expect(firebaseAuth.linkPassword).toHaveBeenCalledWith(account.email, 'a-long-private-password'))
  expect(firebaseAuth.validatePassword).toHaveBeenCalledWith('a-long-private-password')
  expect((await screen.findByRole('status')).textContent).toContain('Senha conectada a esta conta')
  expect(password.value).toBe('')
  expect(confirmation.value).toBe('')
})

it('clears rejected credentials and never displays provider errors or password values', async () => {
  firebaseAuth.linkPassword.mockRejectedValue(new Error('private-password'))
  render(<FirebaseAccountMethods account={account} />)
  const password = await screen.findByLabelText('Nova senha')
  const confirmation = screen.getByLabelText('Confirmar nova senha')
  fireEvent.change(password, { target: { value: 'a-long-private-password' } })
  fireEvent.change(confirmation, { target: { value: 'a-long-private-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar senha' }))
  expect((await screen.findByRole('alert')).textContent).toContain('Não foi possível conectar a senha')
  expect(password.value).toBe('')
  expect(confirmation.value).toBe('')
  expect(screen.queryByText(/private-password|a-long-private-password/)).toBeNull()
})

it('reauthenticates before linking Google and refreshes the Firebase token without account switching', async () => {
  firebaseAuth.getAuthMethods.mockResolvedValue(['password'])
  firebaseAuth.linkGoogle.mockResolvedValue({ verified: true, methods: ['password', 'google.com'] })
  render(<FirebaseAccountMethods account={account} />)
  fireEvent.change(await screen.findByLabelText('Senha atual'), { target: { value: 'current-private-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Conectar Google' }))
  await waitFor(() => expect(firebaseAuth.reauthenticatePassword).toHaveBeenCalledWith('current-private-password'))
  await waitFor(() => expect(firebaseAuth.getToken).toHaveBeenCalledWith(true))
  expect(firebaseAuth.linkGoogle).toHaveBeenCalledOnce()
  expect(screen.queryByText('current-private-password')).toBeNull()
})

it('does not render password actions when the feature flag is unavailable', async () => {
  authService.getConfig.mockResolvedValue({ firebase_enabled: true, firebase_project_id: 'project-test' })
  render(<FirebaseAccountMethods account={account} />)
  await waitFor(() => expect(authService.getConfig).toHaveBeenCalledOnce())
  expect(screen.queryByRole('button', { name: 'Adicionar senha' })).toBeNull()
})
