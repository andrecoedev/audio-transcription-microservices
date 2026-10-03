import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Login from './Login'
import { authService } from '../services/authService'
import { useAuthStore } from '../stores/authStore'

vi.mock('../services/authService', () => ({ authService: { signup: vi.fn(), login: vi.fn() } }))

beforeEach(() => {
  vi.resetAllMocks()
  useAuthStore.setState({ setSession: vi.fn() })
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
    expect(screen.getByRole('link', { name: /criar uma conta/i }).getAttribute('href')).toBe('/signup?saveGuest=1')
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
      <Route path="/" element={<p>USAGI</p>} />
    </Routes></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Usuário'), { target: { value: 'visitor' } })
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
})
