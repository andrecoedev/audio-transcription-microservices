import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import AccountSettings from './AccountSettings'
import { authService } from '../services/authService'
import { useAuthStore } from '../stores/authStore'
import { firebaseAuth } from '../services/firebaseAuth'
import { endSession } from '../services/sessionService'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'

vi.mock('../services/authService', () => ({ authService: { me: vi.fn(), getConfig: vi.fn(), exportData: vi.fn(), deleteAccount: vi.fn() } }))
vi.mock('../services/firebaseAuth', () => ({ firebaseAuth: { reauthenticatePassword: vi.fn(), reauthenticateGoogle: vi.fn(), getTokenContext: vi.fn(), getAuthMethods: vi.fn().mockResolvedValue([]) } }))
vi.mock('../services/sessionService', () => ({ endSession: vi.fn() }))
vi.mock('react-router-dom', () => ({ useNavigate: vi.fn() }))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }))
vi.mock('./GoogleAccountLink', () => ({ default: () => <div>Vínculo Google</div> }))
vi.mock('./LegacyFirebaseMigration', () => ({ default: () => <div>Migração do acesso</div> }))

const account = { id: 7, username: 'conta-teste', display_name: 'Nome da conta', email: 'conta@example.test', auth_provider: 'local' }
beforeEach(() => {
  vi.resetAllMocks()
  authService.getConfig.mockResolvedValue({ firebase_enabled: false })
  useAuthStore.setState({ user: { id: 7, name: 'Nome somente no navegador' }, authProvider: 'local' })
  authService.me.mockResolvedValue({ authenticated: true, user: account })
  authService.exportData.mockResolvedValue({ version: 1, user: { id: 7 } })
  authService.deleteAccount.mockResolvedValue({ account_deleted: true, cleanup_pending: false, identity_cleanup_pending: false })
  firebaseAuth.reauthenticatePassword.mockResolvedValue(undefined)
  firebaseAuth.reauthenticateGoogle.mockResolvedValue({ uid: 'firebase-uid' })
  firebaseAuth.getTokenContext.mockResolvedValue({ token: 'fresh-token', uid: 'firebase-uid' })
  endSession.mockResolvedValue(undefined)
  useNavigate.mockReturnValue(vi.fn())
})

it('downloads the authenticated export as a local JSON file and revokes its object URL', async () => {
  const createObjectURL = vi.fn(() => 'blob:private-export')
  const revokeObjectURL = vi.fn()
  vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  render(<AccountSettings />)
  await screen.findByText('Nome da conta')
  fireEvent.click(screen.getByRole('button', { name: 'Baixar meus dados' }))
  await waitFor(() => expect(authService.exportData).toHaveBeenCalledOnce())
  expect(createObjectURL.mock.calls[0][0]).toBeInstanceOf(Blob)
  expect(createObjectURL.mock.calls[0][0].type).toBe('application/json')
  expect(createObjectURL.mock.calls[0][0].size).toBeGreaterThan(0)
  expect(revokeObjectURL).toHaveBeenCalledWith('blob:private-export')
  click.mockRestore()
  vi.unstubAllGlobals()
})

it('disables export while the private data request is still loading', async () => {
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  let resolveExport
  authService.exportData.mockImplementationOnce(() => new Promise(resolve => { resolveExport = resolve }))
  render(<AccountSettings />)
  await screen.findByText('Nome da conta')
  fireEvent.click(screen.getByRole('button', { name: 'Baixar meus dados' }))
  await waitFor(() => expect(resolveExport).toBeTypeOf('function'))
  expect(screen.getByRole('button', { name: 'Carregando...' }).disabled).toBe(true)
  resolveExport({ version: 1 })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Baixar meus dados' }).disabled).toBe(false))
  click.mockRestore()
})

it('shows a safe export failure without exposing response details', async () => {
  authService.exportData.mockRejectedValueOnce({ status: 503, response: { data: { detail: 'private server details' } } })
  render(<AccountSettings />)
  await screen.findByText('Nome da conta')
  fireEvent.click(screen.getByRole('button', { name: 'Baixar meus dados' }))
  expect((await screen.findByRole('alert')).textContent).toContain('temporariamente indisponível')
  expect(screen.queryByText('private server details')).toBeNull()
})

it('does not send deletion when the user cancels confirmation', async () => {
  render(<AccountSettings />)
  await screen.findByText('Nome da conta')
  fireEvent.click(screen.getByRole('button', { name: 'Excluir minha conta' }))
  expect(screen.getByText(/irreversível/i)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar exclusão' }))
  expect(authService.deleteAccount).not.toHaveBeenCalled()
})

it('requires the exact confirmation phrase and reports cleanup pending after deleting', async () => {
  const navigate = vi.fn()
  useNavigate.mockReturnValue(navigate)
  authService.deleteAccount.mockResolvedValueOnce({ account_deleted: true, cleanup_pending: true, identity_cleanup_pending: true })
  render(<AccountSettings />)
  await screen.findByText('Nome da conta')
  fireEvent.click(screen.getByRole('button', { name: 'Excluir minha conta' }))
  fireEvent.change(screen.getByLabelText('Digite EXCLUIR para confirmar'), { target: { value: 'EXCLUIR' } })
  fireEvent.change(screen.getByLabelText('Senha da conta USAGI'), { target: { value: 'private-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar exclusão' }))
  await waitFor(() => expect(authService.deleteAccount).toHaveBeenCalledWith({ confirmation: 'EXCLUIR', password: 'private-password' }, undefined))
  expect(endSession).toHaveBeenCalledOnce()
  expect(navigate).toHaveBeenCalledWith('/', { replace: true })
  expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/limpeza.*pendente/i))
})

it('keeps the account signed in and gives a safe message when deletion is blocked by processing', async () => {
  authService.deleteAccount.mockRejectedValueOnce({ status: 409, response: { data: { detail: 'internal processing detail' } } })
  render(<AccountSettings />)
  await screen.findByText('Nome da conta')
  fireEvent.click(screen.getByRole('button', { name: 'Excluir minha conta' }))
  fireEvent.change(screen.getByLabelText('Digite EXCLUIR para confirmar'), { target: { value: 'EXCLUIR' } })
  fireEvent.change(screen.getByLabelText('Senha da conta USAGI'), { target: { value: 'private-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar exclusão' }))
  expect((await screen.findByRole('alert')).textContent).toContain('A conta está em uso')
  expect(screen.queryByText('internal processing detail')).toBeNull()
  expect(endSession).not.toHaveBeenCalled()
})

it('reauthenticates Firebase Google with same-account popup before deletion', async () => {
  authService.me.mockResolvedValue({ authenticated: true, user: { ...account, auth_provider: 'firebase' } })
  render(<AccountSettings />)
  await screen.findByText('Gerenciada pelo Google')
  fireEvent.click(screen.getByRole('button', { name: 'Excluir minha conta' }))
  fireEvent.change(screen.getByLabelText('Digite EXCLUIR para confirmar'), { target: { value: 'EXCLUIR' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar exclusão' }))
  await waitFor(() => expect(authService.deleteAccount).toHaveBeenCalledOnce())
  expect(firebaseAuth.reauthenticateGoogle).toHaveBeenCalledOnce()
  expect(firebaseAuth.getTokenContext).toHaveBeenCalledWith(true)
  expect(authService.deleteAccount).toHaveBeenCalledWith({ confirmation: 'EXCLUIR' }, 'fresh-token')
})

it('does not delete after Firebase password reauthentication if the fresh-token UID changed', async () => {
  authService.me.mockResolvedValue({ authenticated: true, user: { ...account, auth_provider: 'firebase', firebase_sign_in_provider: 'password' } })
  firebaseAuth.reauthenticatePassword.mockResolvedValue({ uid: 'firebase-uid' })
  firebaseAuth.getTokenContext.mockResolvedValue({ token: 'fresh-token', uid: 'different-uid' })
  render(<AccountSettings />)
  await screen.findByText(/Gerenciada pelo/)
  fireEvent.click(screen.getByRole('button', { name: 'Excluir minha conta' }))
  fireEvent.change(screen.getByLabelText('Digite EXCLUIR para confirmar'), { target: { value: 'EXCLUIR' } })
  fireEvent.change(screen.getByLabelText('Senha da conta'), { target: { value: 'private-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar exclusão' }))
  expect((await screen.findByRole('alert')).textContent).toContain('A conta mudou')
  expect(authService.deleteAccount).not.toHaveBeenCalled()
})
afterEach(cleanup)

it('shows authoritative account data, with no fictitious editable profile or password action', async () => {
  render(<AccountSettings />)
  expect(await screen.findByText('Nome da conta')).toBeTruthy()
  expect(screen.getByText('conta@example.test')).toBeTruthy()
  expect(screen.queryByText('Nome somente no navegador')).toBeNull()
  expect(screen.queryByRole('textbox')).toBeNull()
  expect(screen.queryByRole('button', { name: /Salvar|Alterar senha|Redefinir senha/ })).toBeNull()
  expect(screen.getByText('Alteração não disponível')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Ajuda: Senha' }))
  expect(screen.getByRole('tooltip').textContent).toContain('ainda não estão disponíveis')
})

it('offers Google security management only for the verified Google sign-in method', async () => {
  authService.me.mockResolvedValue({ authenticated: true, user: { ...account, auth_provider: 'firebase' } })
  render(<AccountSettings />)
  expect(await screen.findByText('Gerenciada pelo Google')).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Gerenciar no Google' }).getAttribute('href')).toBe('https://myaccount.google.com/security')
  expect(screen.queryByRole('textbox')).toBeNull()
})

it('does not infer Google management when the backend identifies password sign-in', async () => {
  authService.me.mockResolvedValue({ authenticated: true, user: { ...account, auth_provider: 'firebase', firebase_sign_in_provider: 'password' } })
  const { container } = render(<AccountSettings />)
  expect(await screen.findByText('Gerenciada pelo método conectado')).toBeTruthy()
  expect(screen.queryByText('Gerenciada pelo Google')).toBeNull()
  expect(screen.queryByRole('link', { name: 'Gerenciar no Google' })).toBeNull()
  expect(container.textContent).not.toMatch(/Firebase|PostgreSQL|UID|conta local/i)
})

it('does not fetch private account data for Guest', () => {
  useAuthStore.setState({ user: null })
  render(<AccountSettings />)
  expect(screen.getByText('Entre na sua conta para ver estes dados.')).toBeTruthy()
  expect(authService.me).not.toHaveBeenCalled()
})

it('rejects an identity mismatch and never exposes returned account details', async () => {
  authService.me.mockResolvedValue({ authenticated: true, user: { ...account, id: 8 } })
  render(<AccountSettings />)
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.queryByText('conta@example.test')).toBeNull()
})

it('shows a safe retry after a failed lookup', async () => {
  authService.me.mockRejectedValueOnce(new Error('private response'))
  render(<AccountSettings />)
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.queryByText('private response')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
  expect(await screen.findByText('Nome da conta')).toBeTruthy()
  expect(authService.me).toHaveBeenCalledTimes(2)
})

it('hides the previous account while a switched identity is loading', async () => {
  const view = render(<AccountSettings />)
  await screen.findByText('Nome da conta')
  let resolveNext
  authService.me.mockImplementation(() => new Promise(resolve => { resolveNext = resolve }))
  useAuthStore.setState({ user: { id: 8 } })
  view.rerender(<AccountSettings />)
  expect(screen.queryByText('conta@example.test')).toBeNull()
  await waitFor(() => expect(resolveNext).toBeTypeOf('function'))
  resolveNext({ authenticated: true, user: { ...account, id: 8, display_name: 'Outra conta' } })
  expect(await screen.findByText('Outra conta')).toBeTruthy()
})
