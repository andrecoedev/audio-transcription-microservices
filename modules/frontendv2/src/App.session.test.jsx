import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App'
import { restoreSession } from './services/sessionService'
import { firebaseAuth } from './services/firebaseAuth'
import { useAuthStore } from './stores/authStore'

vi.mock('./services/sessionService', () => ({ restoreSession: vi.fn() }))
vi.mock('./services/firebaseAuth', () => ({ firebaseAuth: { observe: vi.fn() } }))
vi.mock('./pages/Home', () => ({ default: () => <h1>Início verificado</h1> }))
vi.mock('./components/Layout', async () => {
  const { Outlet } = await import('react-router-dom')
  return { default: () => <Outlet /> }
})
vi.mock('react-hot-toast', () => ({ Toaster: () => null }))

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  sessionStorage.clear()
  window.history.replaceState({}, '', '/?context=preserved')
  useAuthStore.getState().setFirebaseSession({ id: 7 })
  firebaseAuth.observe.mockResolvedValue(vi.fn())
})
afterEach(cleanup)

it('gates rendering during a temporary verification failure and retries in the same context', async () => {
  sessionStorage.setItem('usagi-guest-session', 'synthetic-guest-context')
  restoreSession.mockRejectedValueOnce({ status: 503 }).mockResolvedValue(undefined)
  render(<App />)
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.queryByText('Início verificado')).toBeNull()
  expect(useAuthStore.getState().authProvider).toBe('firebase')
  fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
  expect(await screen.findByText('Início verificado')).toBeTruthy()
  expect(window.location.search).toBe('?context=preserved')
  expect(sessionStorage.getItem('usagi-guest-session')).toBe('synthetic-guest-context')
})

it('receives cross-tab SDK logout and does not reverify ordinary token renewal', async () => {
  let observer
  restoreSession.mockResolvedValue(undefined)
  firebaseAuth.observe.mockImplementation(async callback => { observer = callback; return vi.fn() })
  render(<App />)
  await screen.findByText('Início verificado')
  await waitFor(() => expect(observer).toBeTypeOf('function'))
  observer(true, 'first')
  observer(true, 'first')
  expect(restoreSession).toHaveBeenCalledOnce()
  observer(false, null)
  await waitFor(() => expect(useAuthStore.getState().isAuthenticated).toBe(false))
})

it('reverifies the internal identity if the SDK account changes in another tab', async () => {
  let observer
  restoreSession.mockResolvedValue(undefined)
  firebaseAuth.observe.mockImplementation(async callback => { observer = callback; return vi.fn() })
  render(<App />)
  await screen.findByText('Início verificado')
  await waitFor(() => expect(observer).toBeTypeOf('function'))
  observer(true, 'first')
  observer(true, 'second')
  await waitFor(() => expect(restoreSession).toHaveBeenCalledTimes(2))
})
