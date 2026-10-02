import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import MeetingActionsPanel from './MeetingActionsPanel'
import { audioService } from '../services/audioService'

vi.mock('../services/audioService', () => ({ audioService: {
  getMeetingActions: vi.fn(), createMeetingAction: vi.fn(), updateMeetingAction: vi.fn(), deleteMeetingAction: vi.fn(),
} }))

let actions
beforeEach(() => {
  vi.clearAllMocks()
  actions = []
  audioService.getMeetingActions.mockImplementation(async () => ({ action_items: [...actions] }))
  audioService.createMeetingAction.mockImplementation(async (_id, values) => {
    const item = { id: 1, status: 'open', source: 'manual', ...values }
    actions.push(item)
    return item
  })
  audioService.updateMeetingAction.mockImplementation(async (_id, actionId, values) => {
    actions = actions.map(item => item.id === actionId ? { ...item, ...values } : item)
    return actions.find(item => item.id === actionId)
  })
  audioService.deleteMeetingAction.mockImplementation(async () => { actions = [] })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('creates a manual task without intelligence and retains it after reload', async () => {
  const view = render(<MeetingActionsPanel meetingId="42" />)
  await screen.findByText('Nenhuma tarefa criada.')
  fireEvent.change(screen.getByLabelText('Nova tarefa descrição'), { target: { value: '  Enviar slides  ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Criar tarefa' }))
  expect(await screen.findByText('Enviar slides')).toBeTruthy()
  expect(audioService.createMeetingAction).toHaveBeenCalledWith('42', { description: 'Enviar slides', assignee: null, due_date: null })
  view.unmount()
  render(<MeetingActionsPanel meetingId="42" />)
  expect(await screen.findByText('Enviar slides')).toBeTruthy()
  expect(screen.getByText(/Criada manualmente/)).toBeTruthy()
})

it('edits fields, completes, reopens, dismisses and explicitly deletes a task', async () => {
  actions = [{ id: 1, description: 'Original', assignee: 'Bruno', due_date: '2026-10-05', status: 'open' }]
  render(<MeetingActionsPanel meetingId="42" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Editar tarefa' }))
  fireEvent.change(screen.getByLabelText('Editar tarefa descrição'), { target: { value: 'Revisada' } })
  fireEvent.change(screen.getByLabelText('Editar tarefa responsável'), { target: { value: '' } })
  fireEvent.change(screen.getByLabelText('Editar tarefa prazo'), { target: { value: '' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar tarefa' }))
  await waitFor(() => expect(audioService.updateMeetingAction).toHaveBeenCalledWith('42', 1, { description: 'Revisada', assignee: null, due_date: null }))
  await screen.findByText('Revisada')
  await waitFor(() => expect(screen.getByRole('button', { name: 'Concluir' }).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Concluir' }))
  expect(await screen.findByText(/Concluída/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Reabrir' }))
  await screen.findByText(/Aberta/)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Descartar' }).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Descartar' }))
  expect(await screen.findByText(/Descartada/)).toBeTruthy()
  expect(screen.getByText('Revisada')).toBeTruthy()
  vi.spyOn(window, 'confirm').mockReturnValue(false)
  fireEvent.click(screen.getByRole('button', { name: 'Excluir tarefa' }))
  expect(audioService.deleteMeetingAction).not.toHaveBeenCalled()
  window.confirm.mockReturnValue(true)
  fireEvent.click(screen.getByRole('button', { name: 'Excluir tarefa' }))
  expect(await screen.findByText('Nenhuma tarefa criada.')).toBeTruthy()
})

it('shows loading and retries a failed read', async () => {
  audioService.getMeetingActions.mockRejectedValueOnce(new Error('Internal details'))
  render(<MeetingActionsPanel meetingId="42" />)
  expect(screen.getByRole('status')).toBeTruthy()
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.queryByText('Internal details')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Atualizar tarefas' }))
  expect(await screen.findByText('Nenhuma tarefa criada.')).toBeTruthy()
})

it('preserves the edit form and task when saving fails', async () => {
  actions = [{ id: 1, description: 'Original', assignee: null, due_date: null, status: 'open' }]
  audioService.updateMeetingAction.mockRejectedValueOnce(new Error('Unavailable'))
  render(<MeetingActionsPanel meetingId="42" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Editar tarefa' }))
  fireEvent.change(screen.getByLabelText('Editar tarefa descrição'), { target: { value: 'Changed' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar tarefa' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('Editar tarefa descrição').value).toBe('Changed')
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar edição' }))
  expect(within(screen.getByRole('list')).getByText('Original')).toBeTruthy()
  expect(audioService.updateMeetingAction).toHaveBeenCalledTimes(1)
})
