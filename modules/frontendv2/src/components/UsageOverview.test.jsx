import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import UsageOverview from './UsageOverview'
import { usageService } from '../services/usageService'
import { useAuthStore } from '../stores/authStore'
import { formatTimestamp } from '../utils/format'

vi.mock('../services/usageService', () => ({
  usageService: { getOverview: vi.fn() },
}))

afterEach(() => {
  cleanup()
  useAuthStore.setState({ user: null, isAuthenticated: false })
})

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: { id: 'user-1' }, isAuthenticated: true })
})

it('shows exact aggregate duration and adds attempts across operations as operation counts', async () => {
  usageService.getOverview.mockResolvedValue({ after: '2026-01-01T00:00:00Z', before: '2026-02-01T00:00:00Z', metrics: [
    { operation: 'transcription', metric: 'audio_seconds', unit: 'second', quantity_total: '900', observations: 2, unknown_observations: 0 },
    { operation: 'legacy_minutes', metric: 'audio_seconds', unit: 'second', quantity_total: '60', observations: 1, unknown_observations: 0 },
    { operation: 'transcription', metric: 'attempt', unit: 'attempt', quantity_total: '2', observations: 2, unknown_observations: 0 },
    { operation: 'intelligence', metric: 'attempt', unit: 'attempt', quantity_total: '1', observations: 1, unknown_observations: 0 },
  ] })

  render(<UsageOverview />)

  expect(await screen.findByText('16 min')).toBeTruthy()
  expect(screen.getByText('3 operações iniciadas')).toBeTruthy()
  expect(screen.getByText('Áudio registrado')).toBeTruthy()
  expect(screen.getByText('Operações iniciadas')).toBeTruthy()
  expect(screen.getByText(`Período: ${formatTimestamp('2026-01-01T00:00:00Z')} – ${formatTimestamp('2026-02-01T00:00:00Z')}`)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Ajuda: Consumo registrado' }))
  expect(screen.getByRole('tooltip').textContent).toMatch(/inclusive as que falharam/)
  expect(screen.getByText('Contratação de planos ainda não disponível.')).toBeTruthy()
  expect(document.body.textContent).not.toMatch(/R\$|preço|custo/i)
})

it('labels unknown quantities and marks known audio totals as partial when observations are missing', async () => {
  usageService.getOverview.mockResolvedValue({ metrics: [
    { operation: 'transcription', metric: 'audio_seconds', unit: 'second', quantity_total: '300', observations: 2, unknown_observations: 1 },
    { operation: 'intelligence', metric: 'attempt', unit: 'attempt', quantity_total: null, observations: 3, unknown_observations: 3 },
  ] })

  render(<UsageOverview />)

  expect(await screen.findByText('5 min')).toBeTruthy()
  expect(screen.getByText('Soma parcial: há registros sem quantidade informada.')).toBeTruthy()
  expect(screen.getByText('Não informado')).toBeTruthy()
  expect(screen.queryByText('0 min')).toBeNull()
})

it('shows no recorded data without inventing a balance when there are no observations', async () => {
  usageService.getOverview.mockResolvedValue({ metrics: [] })

  render(<UsageOverview />)

  expect(await screen.findByText('Nenhum dado de uso registrado.')).toBeTruthy()
  expect(screen.queryByText(/saldo|crédito|R\$/i)).toBeNull()
  expect(screen.queryByText('0 min')).toBeNull()
})

it('shows a recoverable error and retries the overview request', async () => {
  usageService.getOverview.mockRejectedValueOnce(new Error('private backend detail'))
    .mockResolvedValueOnce({ metrics: [
      { operation: 'transcription', metric: 'attempt', unit: 'attempt', quantity_total: '1', observations: 1, unknown_observations: 0 },
    ] })

  render(<UsageOverview />)

  expect((await screen.findByRole('alert')).textContent).toContain('Não foi possível carregar os dados de uso.')
  expect(screen.queryByText('private backend detail')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
  expect(await screen.findByText('1 operação iniciada')).toBeTruthy()
  expect(usageService.getOverview).toHaveBeenCalledTimes(2)
})

it('does not request usage data for guest sessions', async () => {
  useAuthStore.setState({ user: { id: 'guest-session' }, isAuthenticated: false })

  const { container } = render(<UsageOverview />)

  await waitFor(() => expect(usageService.getOverview).not.toHaveBeenCalled())
  expect(container.firstChild).toBeNull()
})

it('never shows a previous account overview while the next account loads', async () => {
  const requests = []
  usageService.getOverview.mockImplementation(() => new Promise((resolve) => requests.push(resolve)))
  render(<UsageOverview />)
  await waitFor(() => expect(requests).toHaveLength(1))
  act(() => useAuthStore.setState({ user: { id: 'user-2' }, isAuthenticated: true }))
  await waitFor(() => expect(requests).toHaveLength(2))

  await act(async () => requests[0]({ metrics: [
    { operation: 'transcription', metric: 'audio_seconds', unit: 'second', quantity_total: '60', observations: 1, unknown_observations: 0 },
  ] }))
  expect(screen.queryByText('1 min')).toBeNull()
  expect(screen.getByRole('status').textContent).toContain('Carregando')

  await act(async () => requests[1]({ metrics: [
    { operation: 'transcription', metric: 'audio_seconds', unit: 'second', quantity_total: '120', observations: 1, unknown_observations: 0 },
  ] }))
  expect(await screen.findByText('2 min')).toBeTruthy()
  expect(screen.queryByText('1 min')).toBeNull()
})
