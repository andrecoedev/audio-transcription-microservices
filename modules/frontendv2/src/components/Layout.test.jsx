import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, within, waitFor } from '@testing-library/react'
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
    expect(screen.getByRole('link', { name: 'Minhas transcrições' }).getAttribute('href')).toBe('/transcriptions')
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
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
  })
  it('moves focus into the drawer, traps both Tab directions, and returns focus when closed', async () => {
    useAuthStore.setState({ user: { name: 'Fixture', roles: ['user'] }, token: 'synthetic-session', isAuthenticated: true })
    open()
    const toggle = screen.getByRole('button', { name: 'Abrir navegação' })
    fireEvent.click(toggle)
    const dialog = screen.getByRole('dialog', { name: 'Navegação principal' })
    const accountButton = within(dialog).getByRole('button', { name: 'Área da conta' })
    const focusableItems = () => Array.from(dialog.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'))
    await waitFor(() => expect(document.activeElement).toBe(focusableItems()[0]))
    fireEvent.click(accountButton)
    expect(within(dialog).getByRole('button', { name: 'Sair' })).toBeTruthy()
    expect(focusableItems().at(-1)).toBe(accountButton)
    accountButton.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(focusableItems()[0])
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(accountButton)
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(document.activeElement).toBe(toggle))
    expect(document.body.style.overflow).toBe('')
  })
  it('closes on backdrop click and restores focus', async () => {
    open()
    const toggle = screen.getByRole('button', { name: 'Abrir navegação' })
    fireEvent.click(toggle)
    fireEvent.click(screen.getByLabelText('Fechar navegação pelo fundo'))
    await waitFor(() => expect(document.activeElement).toBe(toggle))
    expect(screen.queryByRole('dialog')).toBeNull()
  })
  it('closes mobile navigation when an admin opens the separated admin destination', () => {
    useAuthStore.setState({ user: { name: 'Fixture', roles: ['admin'] }, token: 'synthetic-session', isAuthenticated: true })
    open()
    const toggle = screen.getByRole('button', { name: 'Abrir navegação' })
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    const drawer = screen.getByRole('dialog', { name: 'Navegação principal' })
    fireEvent.click(within(drawer).getByRole('link', { name: 'Administração' }))
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
  })
  it('keeps admin section heading IDs unique when desktop and mobile sidebars are mounted', () => {
    useAuthStore.setState({ user: { name: 'Fixture', roles: ['admin'] }, token: 'synthetic-session', isAuthenticated: true })
    open()
    fireEvent.click(screen.getByRole('button', { name: 'Abrir navegação' }))

    const sections = screen.getAllByRole('region', { name: 'Administração' })
    expect(sections).toHaveLength(2)
    const headingIds = sections.map(section => section.getAttribute('aria-labelledby'))
    expect(new Set(headingIds).size).toBe(2)
    headingIds.forEach(id => {
      expect(document.getElementById(id)?.textContent).toBe('Administração')
      expect(Array.from(document.querySelectorAll('[id]')).filter(element => element.id === id)).toHaveLength(1)
    })
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
