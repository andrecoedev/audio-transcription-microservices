import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import MeetingIntelligencePanel from './MeetingIntelligencePanel'
import { audioService } from '../services/audioService'
import { useAuthStore } from '../stores/authStore'

vi.mock('../services/audioService', () => ({ audioService: {
  getMeetingIntelligenceStatus: vi.fn(), getMeetingIntelligenceResult: vi.fn(), requestMeetingIntelligence: vi.fn(),
} }))

const result = { revision: 1, provider: 'gemini', model: 'fixture', references: [{ segment_order: 0, start: 0, end: 2 }],
  content: { summary: 'Resumo da reunião', topics: [], decisions: [], open_questions: [],
    action_items: [{ description: 'Preparar relatório', assignee: null, due_date: null, evidence: [{ segment_order: 0, quote: 'relatório' }] }] } }

beforeEach(() => { vi.clearAllMocks(); audioService.getMeetingIntelligenceResult.mockResolvedValue(result) })
afterEach(cleanup)

it('requests first generation and displays a sanitized failure', async () => {
  audioService.getMeetingIntelligenceStatus.mockResolvedValue({ configured: true, generation: null, completed_revision: null })
  audioService.requestMeetingIntelligence.mockRejectedValue(new Error('Serviço indisponível'))
  render(<MeetingIntelligencePanel meetingId="42" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Gerar resumo' }))
  expect((await screen.findByRole('alert')).textContent).toContain('Serviço indisponível')
  expect(audioService.requestMeetingIntelligence).toHaveBeenCalledWith('42', false)
})

it('shows null assignee/deadline and retains completed result while regenerating', async () => {
  audioService.getMeetingIntelligenceStatus.mockResolvedValueOnce({ configured: true, generation: { status: 'completed' }, completed_revision: 1 })
    .mockResolvedValue({ configured: true, generation: { status: 'pending' }, completed_revision: 1 })
  audioService.requestMeetingIntelligence.mockResolvedValue({ status: 'pending' })
  render(<MeetingIntelligencePanel meetingId="42" />)
  expect(await screen.findByText('Resumo da reunião')).toBeTruthy()
  expect(screen.getByText(/Não identificado/)).toBeTruthy()
  expect(screen.getByText(/Sem prazo explícito/)).toBeTruthy()
  expect(screen.getByRole('link', { name: '0,0 s–2,0 s' }).getAttribute('href')).toBe('#segment-0')
  fireEvent.click(screen.getByRole('button', { name: 'Gerar novamente' }))
  await waitFor(() => expect(audioService.requestMeetingIntelligence).toHaveBeenCalledWith('42', true))
  expect(await screen.findByRole('status')).toBeTruthy()
  expect(screen.getByText('Resumo da reunião')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Gerar novamente' }).disabled).toBe(true)
})

it('allows explicit retry after failure', async () => {
  audioService.getMeetingIntelligenceStatus.mockResolvedValue({ configured: true, generation: { status: 'failed' }, completed_revision: null })
  audioService.requestMeetingIntelligence.mockResolvedValue({ status: 'pending' })
  render(<MeetingIntelligencePanel meetingId="42" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Tentar novamente' }))
  await waitFor(() => expect(audioService.requestMeetingIntelligence).toHaveBeenCalledWith('42', false))
})

it('uses per-account configured status for a public account', async () => {
  useAuthStore.setState({ user: { registration_source: 'public' }, isAuthenticated: true })
  audioService.getMeetingIntelligenceStatus.mockResolvedValue({ configured: true, generation: null, completed_revision: null })
  audioService.requestMeetingIntelligence.mockResolvedValue({ status: 'pending' })
  render(<MeetingIntelligencePanel meetingId="42" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Gerar resumo' }))
  await waitFor(() => expect(audioService.requestMeetingIntelligence).toHaveBeenCalledWith('42', false))
})
