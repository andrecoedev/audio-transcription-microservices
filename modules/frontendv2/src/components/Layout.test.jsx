import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Layout from './Layout'
import { useAuthStore } from '../stores/authStore'

beforeEach(() => useAuthStore.setState({ user: null, token: null, isAuthenticated: false }))
afterEach(cleanup)

const open = () => render(<MemoryRouter><Routes><Route element={<Layout />}>
  <Route path="/" element={<h1>Conteúdo útil</h1>} />
</Route></Routes></MemoryRouter>)

describe('USAGI application shell', () => {
  it('keeps navigation and useful content available to visitors', () => {
    open()
    expect(screen.getByRole('main').textContent).toContain('Conteúdo útil')
    expect(screen.getByRole('link', { name: 'Tarefas' }).getAttribute('href')).toBe('/tasks')
    expect(screen.getByRole('link', { name: 'Histórico' }).getAttribute('href')).toBe('/transcriptions')
    expect(screen.queryByRole('heading', { name: 'Administração' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Administração' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Área da conta' }).getAttribute('aria-expanded')).toBe('false')
  })
  it.each([
    ['guest', { user: null, token: null, isAuthenticated: false }],
    ['signed-in non-admin', { user: { name: 'Fixture', roles: ['user'] }, token: 'synthetic-session', isAuthenticated: true }],
  ])('does not render an empty admin section for %s', (_label, auth) => {
    useAuthStore.setState(auth)
    open()
    expect(screen.queryByRole('heading', { name: 'Administração' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Administração' })).toBeNull()
  })
  it('renders one separate admin section and link for an authenticated administrator', () => {
    useAuthStore.setState({ user: { name: 'Fixture', roles: ['admin'] }, token: 'synthetic-session', isAuthenticated: true })
    open()
    expect(screen.getAllByRole('heading', { name: 'Administração' })).toHaveLength(1)
    const links = screen.getAllByRole('link', { name: 'Administração' })
    expect(links).toHaveLength(1)
    expect(links[0].getAttribute('href')).toBe('/admin/settings')
  })
  it('opens and dismisses mobile navigation with Escape', () => {
    open()
    const toggle = screen.getByRole('button', { name: 'Abrir navegação' })
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
  })
  it('closes mobile navigation when an admin opens the separated admin destination', () => {
    useAuthStore.setState({ user: { name: 'Fixture', roles: ['admin'] }, token: 'synthetic-session', isAuthenticated: true })
    open()
    const toggle = screen.getByRole('button', { name: 'Abrir navegação' })
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    const adminLinks = screen.getAllByRole('link', { name: 'Administração' })
    fireEvent.click(adminLinks[1])
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
  })
  it('offers an authenticated logout and clears the session', () => {
    useAuthStore.setState({ user: { name: 'Fixture', initials: 'FI' }, token: 'synthetic-session', isAuthenticated: true })
    open()
    fireEvent.click(screen.getByRole('button', { name: 'Área da conta' }))
    expect(screen.getByRole('link', { name: 'Minha conta' }).getAttribute('href')).toBe('/settings')
    fireEvent.click(screen.getByRole('button', { name: 'Sair' }))
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
})
