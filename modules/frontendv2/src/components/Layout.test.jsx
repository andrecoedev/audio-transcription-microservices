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
    expect(screen.getByRole('button', { name: 'Área da conta' }).getAttribute('aria-expanded')).toBe('false')
  })
  it('opens and dismisses mobile navigation with Escape', () => {
    open()
    const toggle = screen.getByRole('button', { name: 'Abrir navegação' })
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    fireEvent.keyDown(window, { key: 'Escape' })
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
