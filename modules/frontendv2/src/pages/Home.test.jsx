import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Home from './Home'
import { useAuthStore } from '../stores/authStore'

vi.mock('./Dashboard', () => ({ default: () => <div>Atividade recente</div> }))
vi.mock('./Guest', () => ({ default: () => null }))

beforeEach(() => useAuthStore.setState({ isAuthenticated: true }))
afterEach(cleanup)

describe('Home', () => {
  it('keeps the signed-in home links and dashboard', () => {
    render(<MemoryRouter><Home /></MemoryRouter>)
    expect(screen.getByRole('navigation', { name: 'Suas áreas' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ver minhas transcrições' }).getAttribute('href')).toBe('/transcriptions')
    expect(screen.getByRole('link', { name: 'Ver minhas reuniões' }).getAttribute('href')).toBe('/meetings')
    expect(screen.getByRole('link', { name: 'Nova transcrição' }).getAttribute('href')).toBe('/new-transcription')
    expect(screen.getByText('Atividade recente')).toBeTruthy()
  })

  it('presents seven visitor scenes with working demo and sign-in routes', () => {
    useAuthStore.setState({ isAuthenticated: false })
    render(<MemoryRouter><Home /></MemoryRouter>)
    const demos = screen.getAllByRole('link', { name: 'Ver demonstração' })
    expect(demos).toHaveLength(2)
    expect(demos.every((link) => link.getAttribute('href') === '/new-transcription')).toBe(true)
    expect(screen.getByRole('link', { name: 'Entrar' }).getAttribute('href')).toBe('/login?returnTo=%2Fnew-transcription')
    expect(screen.getByRole('link', { name: 'Já tenho conta — entrar' }).getAttribute('href')).toBe('/login?returnTo=%2Fnew-transcription')
    expect(document.querySelectorAll('.vh-scene')).toHaveLength(7)
    expect(screen.getByRole('heading', { level: 1, name: 'O que foi dito vira o que fazer.' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Depois, o que importa — e de onde veio.' })).toBeTruthy()
    expect(screen.getByText(/Dados de exemplo. Nenhum áudio seu é enviado./)).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })
})
