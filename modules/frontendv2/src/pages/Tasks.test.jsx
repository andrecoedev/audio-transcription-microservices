import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Tasks from './Tasks'
import { audioService } from '../services/audioService'

vi.mock('../services/audioService', () => ({ audioService: { listMeetings: vi.fn() } }))
vi.mock('../components/MeetingActionsPanel', () => ({ default: ({ meetingId, evidenceBaseUrl }) => <div data-testid="actions-panel">Actions for {meetingId}<a href={`${evidenceBaseUrl}#segment-0`}>Evidence</a></div> }))

const meetings = [
  { id: 21, title: 'Planning sync', created_at: '2026-10-01T12:00:00Z' },
  { id: 22, title: 'Customer interview', created_at: '2026-10-02T12:00:00Z' },
]

beforeEach(() => {
  vi.clearAllMocks()
  audioService.listMeetings.mockImplementation(async ({ skip }) => ({
    meetings: skip ? [{ id: 41, title: 'Next page', created_at: '2026-10-03T12:00:00Z' }] : meetings,
    total: 21,
  }))
})
afterEach(cleanup)

it('selects one meeting and scopes existing task controls to that meeting', async () => {
  render(<MemoryRouter><Tasks /></MemoryRouter>)
  const select = await screen.findByLabelText('Reunião')
  expect(audioService.listMeetings).toHaveBeenCalledWith({ skip: 0, limit: 20 })
  fireEvent.change(select, { target: { value: '22' } })
  expect(screen.getByTestId('actions-panel').textContent).toBe('Actions for 22Evidence')
  expect(screen.getByRole('link', { name: 'Evidence' }).getAttribute('href')).toBe('/meetings/22#segment-0')
  expect(screen.getByRole('link', { name: 'Abrir reunião completa' }).getAttribute('href')).toBe('/meetings/22')
})

it('uses backend pagination when selecting a meeting on another page', async () => {
  render(<MemoryRouter><Tasks /></MemoryRouter>)
  await screen.findByLabelText('Reunião')
  fireEvent.click(screen.getByRole('button', { name: 'Próxima' }))
  await waitFor(() => expect(audioService.listMeetings).toHaveBeenLastCalledWith({ skip: 20, limit: 20 }))
  fireEvent.change(screen.getByLabelText('Reunião'), { target: { value: '41' } })
  expect(screen.getByTestId('actions-panel').textContent).toBe('Actions for 41Evidence')
  expect(screen.getByText(/Página 2/)).toBeTruthy()
})

it('shows a recoverable error without fabricating task totals', async () => {
  audioService.listMeetings.mockRejectedValueOnce(new Error('private detail'))
  render(<MemoryRouter><Tasks /></MemoryRouter>)
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.queryByText('private detail')).toBeNull()
  expect(screen.queryByText(/Abertas|Concluídas|Descartadas/)).toBeNull()
})
