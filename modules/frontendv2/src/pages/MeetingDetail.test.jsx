import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import MeetingDetail from './MeetingDetail'
import { audioService } from '../services/audioService'

vi.mock('../services/audioService', () => ({ audioService: {
  getMeeting: vi.fn(), getMeetingTranscript: vi.fn(), updateMeetingTitle: vi.fn(), renameMeetingSpeaker: vi.fn(), deleteMeeting: vi.fn(),
  getMeetingMinutes: vi.fn(),
} }))
vi.mock('../components/MeetingIntelligencePanel', () => ({ default: ({ initialTab }) => <div data-testid="intelligence-panel">{initialTab}</div> }))
vi.mock('../components/MeetingActionsPanel', () => ({ default: () => <div data-testid="actions-panel">Meeting tasks</div> }))
vi.mock('../components/MeetingMinutesPanel', () => ({ default: () => <div>Meeting minutes</div> }))

beforeEach(() => {
  vi.clearAllMocks()
  audioService.getMeeting.mockResolvedValue({ id: 7, transcription_id: 70, title: 'Product sync', created_at: '2026-10-01T12:00:00Z', duration_seconds: 120,
    status: 'completed', speakers: [{ id: 'SPEAKER_00', display_name: 'Ana' }] })
  audioService.getMeetingTranscript.mockResolvedValue({ segments: [
    { order: 0, speaker: 'SPEAKER_00', speaker_display_name: 'Ana', start: 1, end: 3, text: 'Decidir o lançamento.' },
    { order: 1, speaker: 'SPEAKER_01', speaker_display_name: 'Rui', start: 4, end: 6, text: 'Revisar métricas.' },
  ] })
})
const scrollToDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollTo')
afterEach(() => {
  cleanup()
  window.history.replaceState({}, '', '/')
  if (scrollToDescriptor) Object.defineProperty(HTMLElement.prototype, 'scrollTo', scrollToDescriptor)
  else delete HTMLElement.prototype.scrollTo
})

function renderMeeting() {
  return render(<MemoryRouter initialEntries={['/meetings/7']}><Routes>
    <Route path="/meetings/:id" element={<MeetingDetail />} />
  </Routes></MemoryRouter>)
}

it('searches existing transcript segments and switches the intelligence tab', async () => {
  renderMeeting()
  expect(await screen.findByText('Decidir o lançamento.')).toBeTruthy()
  expect(screen.getByText('Revisar métricas.')).toBeTruthy()
  fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar no áudio' }), { target: { value: 'métricas' } })
  expect(screen.queryByText('Decidir o lançamento.')).toBeNull()
  expect(screen.getByText('Revisar métricas.')).toBeTruthy()
  expect(screen.getByText('1 de 2 segmentos')).toBeTruthy()
  fireEvent.click(screen.getByRole('tab', { name: 'Decisões' }))
  expect(screen.getByTestId('intelligence-panel').textContent).toBe('decisions')
})

it('keeps a long transcript in a bounded scroll region', async () => {
  audioService.getMeetingTranscript.mockResolvedValueOnce({ segments: Array.from({ length: 500 }, (_, order) => ({
    order, speaker: 'SPEAKER_00', speaker_display_name: 'Ana', start: order, end: order + 1, text: `Segmento ${order}`,
  })) })
  renderMeeting()
  expect(await screen.findByText('Segmento 499')).toBeTruthy()
  const transcript = screen.getByLabelText('Segmentos da transcrição')
  expect(transcript.className).toContain('overflow-y-auto')
  expect(transcript.className).toContain('overscroll-contain')
  expect(transcript.closest('.card').parentElement.className).toContain('xl:h-[min(72vh,52rem)]')
  expect(transcript.closest('.card').className).toContain('h-[65vh]')
})

it('scrolls to an evidence segment after opening the meeting from its hash', async () => {
  const scrollTo = vi.fn()
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: scrollTo })
  window.history.replaceState({}, '', '/meetings/7#segment-1')
  renderMeeting()
  expect(await screen.findByText('Revisar métricas.')).toBeTruthy()
  await waitFor(() => expect(scrollTo).toHaveBeenCalledOnce())
})

it('allows maximum-length unbroken meeting titles to wrap', async () => {
  const longTitle = 'm'.repeat(255)
  audioService.getMeeting.mockResolvedValueOnce({ id: 7, title: longTitle, created_at: '2026-10-01T12:00:00Z', speakers: [] })
  renderMeeting()
  const heading = await screen.findByRole('heading', { name: longTitle, level: 1 })
  expect(heading.className).toContain('break-words')
})

it('keeps title and speaker rename controls connected to the existing APIs', async () => {
  renderMeeting()
  await screen.findByText('Decidir o lançamento.')
  expect(screen.getByRole('heading', { name: 'Product sync', level: 1 })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Exportar transcrição' }).getAttribute('href')).toBe('/transcriptions/70')
  fireEvent.click(screen.getByRole('button', { name: 'Editar título' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'Título da reunião' }), { target: { value: 'Product planning' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar título' }))
  expect(audioService.updateMeetingTitle).toHaveBeenCalledWith('7', 'Product planning')
  fireEvent.click(screen.getByText('Falantes'))
  fireEvent.change(screen.getByLabelText('Nome de SPEAKER_00'), { target: { value: 'Ana Silva' } })
  fireEvent.click(screen.getByRole('button', { name: 'Renomear' }))
  expect(audioService.renameMeetingSpeaker).toHaveBeenCalledWith('7', 'SPEAKER_00', 'Ana Silva')
})
