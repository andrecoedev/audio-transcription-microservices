import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import GuestDemo from './GuestDemo'
import { guestService } from '../services/guestService'

vi.mock('../services/guestService', () => ({ guestService: { demo: vi.fn() } }))

const demo = {
  id: 'usagi-demo-v1', is_demo: true, title: 'Reunião de exemplo', description: 'Conversa sintética.', duration_seconds: 90,
  speakers: [{ id: 'SPEAKER_00', display_name: 'Falante 1' }, { id: 'SPEAKER_01', display_name: 'Falante 2' }],
  segments: [
    { order: 0, start: 0, end: 15, speaker: 'SPEAKER_00', text: 'Vamos revisar o projeto.' },
    { order: 1, start: 15, end: 30, speaker: 'SPEAKER_01', text: 'A entrega fica para sexta.' },
  ],
  intelligence: {
    schema_version: '1', summary: 'A equipe revisou o projeto e combinou a próxima entrega.',
    topics: [{ description: 'Planejamento da entrega', evidence: [{ segment_order: 0, quote: 'revisar o projeto' }] }],
    decisions: [], action_items: [{ description: 'Preparar a entrega', assignee: null, due_date: null, evidence: [{ segment_order: 1, quote: 'para sexta' }] }],
    open_questions: [],
  },
}

beforeEach(() => { vi.resetAllMocks() })
afterEach(cleanup)

describe('Guest demo', () => {
  it('loads a clearly labeled read-only synthetic example without file upload controls', async () => {
    guestService.demo.mockResolvedValue(demo)
    render(<MemoryRouter><GuestDemo /></MemoryRouter>)
    expect(await screen.findByText('Reunião de exemplo')).toBeTruthy()
    expect(screen.getByText('Demonstração sintética')).toBeTruthy()
    expect(screen.getByText(/Nenhum áudio é enviado ou processado/)).toBeTruthy()
    expect(screen.getByText('Entre para consultar os serviços disponíveis e salvar suas reuniões.')).toBeTruthy()
    expect(document.querySelector('input[type="file"]')).toBeNull()
    expect(screen.getByRole('link', { name: 'Entrar' }).getAttribute('href')).toBe('/login?returnTo=%2Fnew-transcription')
  })

  it('shows loading, reports failures, and retries the demo request', async () => {
    guestService.demo.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(demo)
    render(<MemoryRouter><GuestDemo /></MemoryRouter>)
    expect(screen.getByRole('status').textContent).toContain('Carregando')
    expect(await screen.findByRole('alert')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(await screen.findByText('Reunião de exemplo')).toBeTruthy()
    expect(guestService.demo).toHaveBeenCalledTimes(2)
  })

  it('filters transcript speakers and focuses the cited segment from evidence', async () => {
    guestService.demo.mockResolvedValue(demo)
    render(<MemoryRouter><GuestDemo /></MemoryRouter>)
    await screen.findByText('Vamos revisar o projeto.')
    fireEvent.change(screen.getByLabelText('Filtrar falante'), { target: { value: 'SPEAKER_01' } })
    expect(screen.queryByText('Vamos revisar o projeto.')).toBeNull()
    expect(screen.getByText('A entrega fica para sexta.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Resumo e análise' }))
    fireEvent.click(await screen.findByRole('button', { name: /Trecho 1:/ }))
    expect(screen.getByRole('button', { name: 'Transcrição' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByText('Vamos revisar o projeto.')).toBeTruthy()
    expect(screen.getByLabelText('Filtrar falante').value).toBe('SPEAKER_00')
    await waitFor(() => expect(document.activeElement).toBe(document.getElementById('demo-segment-0')))
    expect(document.getElementById('demo-segment-0').tabIndex).toBe(-1)
  })
})
