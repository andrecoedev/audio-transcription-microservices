import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import MeetingMinutesPanel from './MeetingMinutesPanel'
import { audioService } from '../services/audioService'

vi.mock('../services/audioService', () => ({ audioService: { getMeetingMinutes: vi.fn(), getMeetingMinutesMarkdown: vi.fn() } }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const minutes = {
  meeting_id: 42,
  title: 'Planning sync',
  created_at: '2026-10-01T12:00:00Z',
  summary: 'Discussed delivery.',
  topics: [{ description: 'Release timeline', evidence: [] }],
  decisions: [{ description: 'Ship on Friday', evidence: [] }],
  action_items: [
    { id: 1, description: 'Send final plan', status: 'open', source: 'ai_reviewed', assignee: 'Ana', due_date: '2026-10-05' },
    { id: 2, description: 'Book room', status: 'done', source: 'manual', assignee: null, due_date: null },
  ],
  open_questions: [{ description: 'Who owns support?', evidence: [] }],
}
const markdown = '# Planning sync\n\n## Action Items\n- [ ] Send final plan\n- [x] Book room\n'
const readBlob = blob => new Promise(resolve => {
  const reader = new FileReader()
  reader.onload = () => resolve(reader.result)
  reader.readAsText(blob)
})

beforeEach(() => {
  vi.clearAllMocks()
  audioService.getMeetingMinutes.mockResolvedValue(minutes)
  audioService.getMeetingMinutesMarkdown.mockResolvedValue(markdown)
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('previews reviewed actions, labels AI content, and exports markdown from the same minutes', async () => {
  const blobs = []
  const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockImplementation(blob => { blobs.push(blob); return 'blob:minutes' })
  const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  render(<MeetingMinutesPanel meetingId="42" />)

  expect(await screen.findByRole('heading', { name: 'Planning sync' })).toBeTruthy()
  expect(screen.getByText('Resumo e demais conteúdos analíticos são gerados por IA; revise antes de utilizar.')).toBeTruthy()
  expect(screen.getByText(/IA → revisada · Ana · 2026-10-05/)).toBeTruthy()
  expect(screen.getByText(/Criada manualmente/)).toBeTruthy()
  expect(screen.queryByText('Quem owns support?')).toBeNull()
  expect(screen.getByText('Who owns support?')).toBeTruthy()

  fireEvent.click(screen.getByRole('button', { name: 'Baixar Markdown' }))
  await waitFor(() => expect(click).toHaveBeenCalledOnce())
  expect(audioService.getMeetingMinutesMarkdown).toHaveBeenCalledWith('42')
  expect(createObjectURL).toHaveBeenCalledWith(expect.objectContaining({ type: 'text/markdown;charset=utf-8' }))
  expect(await readBlob(blobs[0])).toBe(markdown)
  expect(revokeObjectURL).toHaveBeenCalledWith('blob:minutes')

  expect(audioService.getMeetingMinutesMarkdown).toHaveBeenCalledTimes(1)
})

it('copies the exact Markdown body returned by the backend', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  render(<MeetingMinutesPanel meetingId="42" />)
  await screen.findByRole('heading', { name: 'Planning sync' })
  fireEvent.click(screen.getByRole('button', { name: 'Copiar' }))
  await waitFor(() => expect(writeText).toHaveBeenCalledWith(markdown))
  expect(audioService.getMeetingMinutesMarkdown).toHaveBeenCalledWith('42')
})

it('supports manual actions when there is no Intelligence and reloads changed data', async () => {
  const manualOnly = { ...minutes, summary: '', topics: [], decisions: [], open_questions: [], action_items: [
    { id: 3, description: 'Prepare room', status: 'open', source: 'manual' },
  ] }
  audioService.getMeetingMinutes.mockResolvedValue(manualOnly)
  const view = render(<MeetingMinutesPanel meetingId="42" version={0} />)
  expect(await screen.findByText('Prepare room')).toBeTruthy()
  expect(screen.getByText('Nenhum resumo disponível.')).toBeTruthy()
  expect(screen.queryByText(/gerados por IA/)).toBeNull()
  view.rerender(<MeetingMinutesPanel meetingId="42" version={1} />)
  await waitFor(() => expect(audioService.getMeetingMinutes).toHaveBeenCalledTimes(2))
  expect(screen.getByText(/Criada manualmente/)).toBeTruthy()
})

it('shows loading and a recoverable error state', async () => {
  audioService.getMeetingMinutes.mockRejectedValueOnce(new Error('internal detail'))
  render(<MeetingMinutesPanel meetingId="42" />)
  expect(screen.getByRole('status')).toBeTruthy()
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.queryByText('internal detail')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
  expect(await screen.findByRole('heading', { name: 'Planning sync' })).toBeTruthy()
})

it('shows export errors and retries against the backend', async () => {
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:minutes')
  audioService.getMeetingMinutesMarkdown.mockRejectedValueOnce(new Error('server failure'))
  render(<MeetingMinutesPanel meetingId="42" />)
  await screen.findByRole('heading', { name: 'Planning sync' })
  fireEvent.click(screen.getByRole('button', { name: 'Baixar Markdown' }))
  expect(await screen.findByText('Não foi possível exportar a ata. Tente novamente.')).toBeTruthy()
  expect(click).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Copiar' }))
  await waitFor(() => expect(audioService.getMeetingMinutesMarkdown).toHaveBeenCalledTimes(2))
  expect(click).not.toHaveBeenCalled()
})
