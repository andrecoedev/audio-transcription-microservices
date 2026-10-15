import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import App from './App'
import { useAuthStore } from './stores/authStore'
import { restoreSession } from './services/sessionService'
import { firebaseAuth } from './services/firebaseAuth'
import { adminSettingsService } from './services/adminSettingsService'

vi.mock('./services/sessionService', () => ({ restoreSession: vi.fn() }))
vi.mock('./services/firebaseAuth', () => ({ firebaseAuth: { observe: vi.fn() } }))
vi.mock('./components/Layout', async () => {
  const { Outlet } = await import('react-router-dom')
  return { default: () => <Outlet /> }
})
vi.mock('react-hot-toast', () => ({ Toaster: () => null }))
vi.mock('./services/adminSettingsService', () => ({ adminSettingsService: {
  getSettings: vi.fn(), getOverview: vi.fn(), getParticipants: vi.fn(), getHistory: vi.fn(),
  searchAccounts: vi.fn(), initialize: vi.fn(), save: vi.fn(), grant: vi.fn(), revoke: vi.fn(),
} }))

beforeEach(() => {
  vi.resetAllMocks()
  restoreSession.mockResolvedValue(undefined)
  firebaseAuth.observe.mockResolvedValue(vi.fn())
  window.history.replaceState({}, '', '/admin/settings')
  useAuthStore.setState({ isAuthenticated: true, user: { id: 5, roles: [] }, token: 'synthetic-local-proof' })
})
afterEach(cleanup)

it.each([
  ['guest', { isAuthenticated: false, user: null }],
  ['signed-in non-admin', { isAuthenticated: true, user: { id: 5, roles: ['user'] } }],
])('%s cannot fetch admin settings', async (_label, auth) => {
  useAuthStore.setState(auth)
  render(<App />)
  expect(await screen.findByText(auth.isAuthenticated ? 'Acesso restrito' : 'Salve e acompanhe suas reuniões')).toBeTruthy()
  expect(adminSettingsService.getSettings).not.toHaveBeenCalled()
  expect(adminSettingsService.getOverview).not.toHaveBeenCalled()
})

it('loads the admin page for a verified admin role', async () => {
  useAuthStore.setState({ isAuthenticated: true, user: { id: 5, roles: ['admin'] }, token: 'synthetic-local-proof' })
  render(<App />)
  expect(await screen.findByText('Administração')).toBeTruthy()
  expect(adminSettingsService.getSettings).toHaveBeenCalledOnce()
})
