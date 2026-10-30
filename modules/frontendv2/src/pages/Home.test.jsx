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
  it('points authenticated users to a new transcription, their transcriptions, and meetings', () => {
    render(<MemoryRouter><Home /></MemoryRouter>)
    expect(screen.getByRole('navigation', { name: 'Suas áreas' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ver minhas transcrições' }).getAttribute('href')).toBe('/transcriptions')
    expect(screen.getByRole('link', { name: 'Ver minhas reuniões' }).getAttribute('href')).toBe('/meetings')
    expect(screen.getByText('Atividade recente')).toBeTruthy()
  })

  it('offers the example demo and a neutral login link to visitors', () => {
    useAuthStore.setState({ isAuthenticated: false })
    render(<MemoryRouter><Home /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Ver demonstração' }).getAttribute('href')).toBe('/new-transcription')
    expect(screen.getByRole('link', { name: 'Entrar' }).getAttribute('href')).toBe('/login?returnTo=%2Fnew-transcription')
    expect(screen.queryByRole('navigation', { name: 'Próximos passos' })).toBeNull()
  })
})
