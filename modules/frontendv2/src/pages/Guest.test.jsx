import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Guest from './Guest'
import { guestService } from '../services/guestService'
import { useAuthStore } from '../stores/authStore'

vi.mock('../services/guestService', () => ({ guestService: {
  policy: vi.fn(), session: vi.fn(), result: vi.fn(), createSession: vi.fn(), createJob: vi.fn(), claim: vi.fn(), delete: vi.fn(),
} }))

beforeEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  useAuthStore.setState({ user: { id: 1 }, token: 'account-token', isAuthenticated: true })
  sessionStorage.setItem('usagi-guest-session', JSON.stringify({ guest_token: 'guest-proof', resultId: 7 }))
  guestService.result.mockResolvedValue({ id: 7, status: 'completed', segments: [{ start: 0, end: 1, text: 'Guest result' }] })
  guestService.claim.mockResolvedValue({ transferred: 1 })
})
afterEach(cleanup)

describe('Guest result ownership', () => {
  it('requires an explicit claim before transferring the temporary result', async () => {
    render(<MemoryRouter><Routes><Route path="/" element={<Guest />} /><Route path="/transcriptions/7" element={<p>Saved transcription</p>} /></Routes></MemoryRouter>)
    expect(await screen.findByRole('button', { name: 'Salvar na minha conta' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Salve sua transcrição anterior' })).toBeTruthy()
    expect(guestService.claim).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Salvar na minha conta' }))
    expect(await screen.findByText('Saved transcription')).toBeTruthy()
    expect(guestService.claim).toHaveBeenCalledWith('guest-proof')
    expect(sessionStorage.getItem('usagi-guest-session')).toBeNull()
  })

  it('shows queued state from the actual result API without invented progress', async () => {
    guestService.result.mockResolvedValueOnce({ id: 7, status: 'queued', segments: [] })
    render(<MemoryRouter><Guest /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Na fila' })).toBeTruthy()
    expect(screen.queryByText(/%|minuto|segundo/i)).toBeNull()
  })
})
