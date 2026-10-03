import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import MeetingActionsPanel from './MeetingActionsPanel'
import { audioService } from '../services/audioService'

vi.mock('../services/audioService', () => ({ audioService: {
  getMeetingActions: vi.fn(), getMeetingIntelligenceStatus: vi.fn(), getMeetingIntelligenceResult: vi.fn(),
  createMeetingAction: vi.fn(), acceptMeetingActionSuggestion: vi.fn(), dismissMeetingActionSuggestion: vi.fn(),
  updateMeetingAction: vi.fn(), deleteMeetingAction: vi.fn(),
} }))

const intelligence = { revision: 1, provider: 'gemini', model: 'fixture', references: [{ segment_order: 0, start: 0, end: 2 }],
  content: { action_items: [{ description: 'Preparar relatório', assignee: 'Ana', due_date: null,
    evidence: [{ segment_order: 0, quote: 'preparar relatório' }] }] } }
let actions
let reviews

beforeEach(() => {
  vi.clearAllMocks()
  actions = []
  reviews = []
  audioService.getMeetingActions.mockImplementation(async () => ({ action_items: [...actions], suggestion_reviews: [...reviews] }))
  audioService.getMeetingIntelligenceStatus.mockResolvedValue({ completed_revision: 1 })
  audioService.getMeetingIntelligenceResult.mockResolvedValue(intelligence)
  audioService.createMeetingAction.mockImplementation(async (_id, values) => {
    const item = { id: 1, status: 'open', source: 'manual', ...values }
    actions.push(item)
    return item
  })
  audioService.acceptMeetingActionSuggestion.mockImplementation(async (_id, revision, sourceIndex, changes) => {
    const item = { id: 2, status: 'open', source: 'ai_reviewed', source_revision: revision, source_index: sourceIndex,
      original_description: intelligence.content.action_items[sourceIndex].description,
      evidence: intelligence.content.action_items[sourceIndex].evidence,
      description: intelligence.content.action_items[sourceIndex].description, assignee: 'Ana', due_date: null, ...changes }
    actions.push(item)
    reviews.push({ source_revision: revision, source_index: sourceIndex, status: 'accepted' })
    return item
  })
  audioService.dismissMeetingActionSuggestion.mockImplementation(async (_id, revision, sourceIndex) => {
    reviews.push({ source_revision: revision, source_index: sourceIndex, status: 'dismissed' })
  })
  audioService.updateMeetingAction.mockImplementation(async (_id, actionId, changes) => {
    actions = actions.map(item => item.id === actionId ? { ...item, ...changes } : item)
    return actions.find(item => item.id === actionId)
  })
  audioService.deleteMeetingAction.mockImplementation(async (_id, actionId) => { actions = actions.filter(item => item.id !== actionId) })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('shows a suggestion, accepts it explicitly, edits and retains it after reload', async () => {
  const view = render(<MeetingActionsPanel meetingId="42" />)
  expect(await screen.findByText('Preparar relatório')).toBeTruthy()
  expect(screen.getByRole('link', { name: '0.0s–2.0s' }).getAttribute('href')).toBe('#segment-0')
  fireEvent.click(screen.getByRole('button', { name: 'Aceitar' }))
  expect(await screen.findByText(/IA → revisada/)).toBeTruthy()
  expect(audioService.acceptMeetingActionSuggestion).toHaveBeenCalledWith('42', 1, 0, {})
  expect(screen.queryByText('Preparar relatório', { selector: 'li p' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Editar tarefa' }))
  fireEvent.change(screen.getByLabelText('Editar tarefa descrição'), { target: { value: 'Preparar relatório final' } })
  fireEvent.change(screen.getByLabelText('Editar tarefa prazo'), { target: { value: '2026-10-05' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar tarefa' }))
  await waitFor(() => expect(audioService.updateMeetingAction).toHaveBeenCalledWith('42', 2, {
    description: 'Preparar relatório final', assignee: 'Ana', due_date: '2026-10-05',
  }))
  expect(await screen.findByText('Preparar relatório final')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Ver sugestão original (revisão 1)' }))
  expect(await screen.findByRole('region', { name: 'Origem da tarefa' })).toBeTruthy()
  expect(audioService.getMeetingIntelligenceResult).toHaveBeenLastCalledWith('42', 1)
  view.unmount()
  render(<MeetingActionsPanel meetingId="42" />)
  expect(await screen.findByText('Preparar relatório final')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Aceitar' })).toBeNull()
})

it('keeps evidence links pointed at the meeting from task lists and reviewed origins', async () => {
  render(<MeetingActionsPanel meetingId="42" evidenceBaseUrl="/meetings/42" />)
  const suggestionEvidence = await screen.findByRole('link', { name: '0.0s–2.0s' })
  expect(suggestionEvidence.getAttribute('href')).toBe('/meetings/42#segment-0')
  fireEvent.click(screen.getByRole('button', { name: 'Aceitar' }))
  fireEvent.click(await screen.findByRole('button', { name: /Ver sugestão original/ }))
  const origin = await screen.findByRole('region', { name: 'Origem da tarefa' })
  expect(within(origin).getByRole('link').getAttribute('href')).toBe('/meetings/42#segment-0')
})

it('edits before accepting and dismisses suggestions persistently', async () => {
  const view = render(<MeetingActionsPanel meetingId="42" />)
  await screen.findByText('Preparar relatório')
  fireEvent.click(screen.getByRole('button', { name: 'Editar e aceitar' }))
  fireEvent.change(screen.getByLabelText('Editar sugestão descrição'), { target: { value: 'Enviar relatório final' } })
  fireEvent.change(screen.getByLabelText('Editar sugestão prazo'), { target: { value: '2026-10-05' } })
  fireEvent.click(screen.getByRole('button', { name: 'Aceitar tarefa revisada' }))
  await waitFor(() => expect(audioService.acceptMeetingActionSuggestion).toHaveBeenCalledWith('42', 1, 0, {
    description: 'Enviar relatório final', assignee: 'Ana', due_date: '2026-10-05',
  }))
  view.unmount()
  actions = []
  reviews = []
  const dismissed = render(<MeetingActionsPanel meetingId="42" />)
  await screen.findByText('Preparar relatório')
  fireEvent.click(screen.getByRole('button', { name: 'Descartar sugestão' }))
  await waitFor(() => expect(audioService.dismissMeetingActionSuggestion).toHaveBeenCalledWith('42', 1, 0))
  dismissed.unmount()
  render(<MeetingActionsPanel meetingId="42" />)
  await screen.findByText('Nenhuma sugestão pendente nesta revisão.')
  expect(screen.queryByText('Preparar relatório')).toBeNull()
})

it('shows new revision suggestions without replacing previously reviewed work', async () => {
  actions = [{ id: 2, status: 'done', source: 'ai_reviewed', source_revision: 1, source_index: 0,
    description: 'Enviar slides finais', original_description: 'Enviar slides', assignee: 'Bruno', due_date: '2026-10-05' }]
  reviews = [{ source_revision: 1, source_index: 0, status: 'accepted' }]
  const revised = { ...intelligence, revision: 2, content: { action_items: [
    { description: 'Enviar apresentação revisada', assignee: 'Bruno', due_date: null, evidence: [{ segment_order: 0, quote: 'apresentação' }] },
    { description: 'Agendar retorno', assignee: null, due_date: null, evidence: [{ segment_order: 0, quote: 'retorno' }] },
  ] } }
  audioService.getMeetingIntelligenceStatus.mockResolvedValue({ completed_revision: 2 })
  audioService.getMeetingIntelligenceResult.mockResolvedValue(revised)
  render(<MeetingActionsPanel meetingId="42" />)
  expect(await screen.findByText('Enviar apresentação revisada')).toBeTruthy()
  expect(screen.getByText('Agendar retorno')).toBeTruthy()
  expect(screen.getByText('Enviar slides finais')).toBeTruthy()
  expect(screen.getByText(/Concluída/)).toBeTruthy()
  expect(audioService.updateMeetingAction).not.toHaveBeenCalled()
})

it('creates manual work without intelligence and retains it after reload', async () => {
  audioService.getMeetingIntelligenceStatus.mockResolvedValue({ completed_revision: null })
  const view = render(<MeetingActionsPanel meetingId="42" />)
  await screen.findByText('Ainda não há análise da reunião.')
  fireEvent.change(screen.getByLabelText('Nova tarefa descrição'), { target: { value: '  Enviar slides  ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Criar tarefa' }))
  expect(await screen.findByText('Enviar slides')).toBeTruthy()
  expect(audioService.createMeetingAction).toHaveBeenCalledWith('42', { description: 'Enviar slides', assignee: null, due_date: null })
  view.unmount()
  actions = [{ id: 1, status: 'open', source: 'manual', description: 'Enviar slides', assignee: null, due_date: null }]
  render(<MeetingActionsPanel meetingId="42" />)
  expect(await screen.findByText('Enviar slides')).toBeTruthy()
  expect(screen.getByText(/Criada manualmente/)).toBeTruthy()
})

it('keeps action field labels stacked with aligned full-width inputs', async () => {
  render(<MeetingActionsPanel meetingId="42" />)
  const description = await screen.findByLabelText('Nova tarefa descrição')
  const assignee = screen.getByLabelText('Nova tarefa responsável')
  const dueDate = screen.getByLabelText('Nova tarefa prazo')
  const fields = description.closest('label').parentElement

  expect(fields.className).toContain('sm:grid-cols-2')
  expect(description.closest('label').className).toContain('sm:col-span-2')
  for (const input of [description, assignee, dueDate]) {
    expect(input.closest('label').className).toContain('flex-col')
    expect(input.className).toContain('min-w-0')
    expect(input.className).toContain('input')
    expect(input.className).toContain('h-10')
    expect(input.className).toContain('mt-auto')
  }
})

it('completes and reopens tasks, then honors explicit deletion', async () => {
  actions = [{ id: 1, description: 'Original', assignee: 'Bruno', due_date: '2026-10-05', status: 'open' }]
  render(<MeetingActionsPanel meetingId="42" />)
  const original = await screen.findByText('Original')
  const row = original.closest('li')
  fireEvent.click(within(row).getByRole('button', { name: 'Concluir' }))
  expect(await within(row).findByText(/Concluída/)).toBeTruthy()
  fireEvent.click(within(row).getByRole('button', { name: 'Reabrir' }))
  expect(await within(row).findByText(/Aberta/)).toBeTruthy()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  fireEvent.click(within(row).getByRole('button', { name: 'Excluir tarefa' }))
  expect(await screen.findByText('Nenhuma tarefa criada.')).toBeTruthy()
})

it('shows loading and a sanitized error, then retries', async () => {
  audioService.getMeetingActions.mockRejectedValueOnce(new Error('Internal details'))
  render(<MeetingActionsPanel meetingId="42" />)
  expect(screen.getByRole('status')).toBeTruthy()
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.queryByText('Internal details')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Atualizar tarefas' }))
  expect(await screen.findByText('Preparar relatório')).toBeTruthy()
})

it('preserves the edit form when saving fails', async () => {
  actions = [{ id: 1, description: 'Original', assignee: null, due_date: null, status: 'open' }]
  audioService.updateMeetingAction.mockRejectedValueOnce(new Error('Unavailable'))
  render(<MeetingActionsPanel meetingId="42" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Editar tarefa' }))
  fireEvent.change(screen.getByLabelText('Editar tarefa descrição'), { target: { value: 'Changed' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar tarefa' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('Editar tarefa descrição').value).toBe('Changed')
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar edição' }))
  expect(within(screen.getByRole('list').lastElementChild).getByText('Original')).toBeTruthy()
  expect(audioService.updateMeetingAction).toHaveBeenCalledTimes(1)
})
