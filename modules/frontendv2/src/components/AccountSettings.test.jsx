import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import AccountSettings from './AccountSettings'
import { authService } from '../services/authService'
import { useAuthStore } from '../stores/authStore'

vi.mock('../services/authService', () => ({ authService: { me: vi.fn(), getConfig: vi.fn() } }))
vi.mock('./GoogleAccountLink', () => ({ default: () => <div>Vínculo Google</div> }))
vi.mock('./LegacyFirebaseMigration', () => ({ default: () => <div>Migração do acesso</div> }))

const account = { id: 7, username: 'conta-teste', display_name: 'Nome da conta', email: 'conta@example.test', auth_provider: 'local' }
beforeEach(() => {
  vi.resetAllMocks()
  authService.getConfig.mockResolvedValue({ firebase_enabled: false })
  useAuthStore.setState({ user: { id: 7, name: 'Nome somente no navegador' }, authProvider: 'local' })
  authService.me.mockResolvedValue({ authenticated: true, user: account })
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
  render(<AccountSettings />)
  expect(await screen.findByText('Gerenciada pelo Firebase')).toBeTruthy()
  expect(screen.queryByText('Gerenciada pelo Google')).toBeNull()
  expect(screen.queryByRole('link', { name: 'Gerenciar no Google' })).toBeNull()
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
