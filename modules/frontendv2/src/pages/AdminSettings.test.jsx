import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import AdminSettings from './AdminSettings'
import { adminSettingsService } from '../services/adminSettingsService'

vi.mock('../services/adminSettingsService', () => ({ adminSettingsService: {
  getSettings: vi.fn(), getOverview: vi.fn(), getParticipants: vi.fn(), getHistory: vi.fn(),
  searchAccounts: vi.fn(), initialize: vi.fn(), save: vi.fn(), grant: vi.fn(), revoke: vi.fn(),
} }))

const settings = (values = {}) => ({ configured: true, version: 2,
  values: { 'beta.enabled': false, 'beta.round_name': 'Beta fechado', 'beta.round_id': 'round-one',
    'beta.max_participants': 5, 'beta.quota_minutes_per_participant': 60, 'assemblyai.platform_enabled': false,
    'assemblyai.hard_stop_usd': '0', 'assemblyai.alert_usd': '0', 'assemblyai.model': 'universal-3-5-pro',
    'assemblyai.speaker_detection': true, 'limits.max_audio_seconds': 600, 'limits.max_upload_mb': 100,
    ...values }, saved_values: {}, overrides: {}, updated_at: null,
  definitions: [
    { key: 'beta.enabled', type: 'boolean', description: 'Autoriza a rodada.', default: false, editable: true, requires_confirmation: true },
    { key: 'beta.round_name', type: 'string', description: 'Nome da rodada.', default: 'Beta fechado', editable: true, requires_confirmation: false },
    { key: 'beta.round_id', type: 'string', description: 'ID da rodada.', default: '', editable: true, requires_confirmation: true },
    { key: 'beta.max_participants', type: 'int', description: 'Vagas.', default: 5, minimum: 1, maximum: 5, editable: true, requires_confirmation: false },
    { key: 'beta.quota_minutes_per_participant', type: 'int', description: 'Cota.', default: 60, minimum: 0, maximum: 600, editable: true, requires_confirmation: true },
    { key: 'assemblyai.platform_enabled', type: 'boolean', description: 'Uso da credencial.', default: false, editable: true, requires_confirmation: true },
    { key: 'assemblyai.hard_stop_usd', type: 'decimal', description: 'Teto interno.', default: '0', editable: true, requires_confirmation: true },
    { key: 'assemblyai.alert_usd', type: 'decimal', description: 'Alerta interno.', default: '0', editable: true, requires_confirmation: false },
    { key: 'assemblyai.model', type: 'enum', description: 'Modelo fixo.', default: 'universal-3-5-pro', editable: false, options: ['universal-3-5-pro'] },
    { key: 'assemblyai.speaker_detection', type: 'boolean', description: 'Detecção fixa.', default: true, editable: false },
    { key: 'limits.max_audio_seconds', type: 'int', description: 'Duração.', default: 600, minimum: 1, maximum: 600, editable: true },
    { key: 'limits.max_upload_mb', type: 'int', description: 'Upload.', default: 100, minimum: 1, maximum: 100, editable: true },
  ] })

beforeEach(() => {
  vi.resetAllMocks()
  adminSettingsService.getSettings.mockResolvedValue(settings())
  adminSettingsService.getOverview.mockResolvedValue({ participants_used: 0, participants_maximum: 5, consumed_seconds: '0', reserved_seconds: '0',
    financial: { authorized_usd: '0', available_usd: '0', committed_above_limit: false, alert_reached: false, review_required: false, unresolved_calls: 0, queued_calls: 0 },
    system: { database: 'connected', assemblyai_credential_configured: true, firebase_configured: true } })
  adminSettingsService.getParticipants.mockResolvedValue({ items: [], used_slots: 0, maximum: 5 })
  adminSettingsService.getHistory.mockResolvedValue({ items: [] })
})
afterEach(cleanup)

it('loads the settings, keeps model fixed, and shows credential configuration without provider checks', async () => {
  render(<AdminSettings />)
  expect(await screen.findByText('Universal-3.5 Pro')).toBeTruthy()
  expect(screen.getByText('Configurada')).toBeTruthy()
  expect(screen.queryByText('universal-3-5-pro')).toBeNull()
  expect(adminSettingsService.getSettings).toHaveBeenCalledOnce()
})

it('requires explicit confirmation for activation and leaves the draft unchanged when canceled', async () => {
  render(<AdminSettings />)
  await screen.findByText('Visão geral')
  fireEvent.change(screen.getByRole('combobox', { name: 'enabled' }), { target: { value: 'true' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar Beta fechado' }))
  expect(await screen.findByRole('dialog')).toBeTruthy()
  expect(adminSettingsService.save).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(adminSettingsService.save).not.toHaveBeenCalled()
})

it('saves an activation only after confirmation', async () => {
  adminSettingsService.save.mockResolvedValue(settings({ 'beta.enabled': true }))
  render(<AdminSettings />)
  await screen.findByText('Visão geral')
  fireEvent.change(screen.getByRole('combobox', { name: 'enabled' }), { target: { value: 'true' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar Beta fechado' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
  expect(await screen.findByText('Alteração salva.')).toBeTruthy()
  expect(adminSettingsService.save).toHaveBeenCalledWith('beta', 2, true, { enabled: true })
})

it('keeps a draft after a version conflict and saves only after explicit confirmation', async () => {
  const current = settings()
  adminSettingsService.save.mockRejectedValueOnce(Object.assign(new Error('conflict'), { status: 409 }))
  render(<AdminSettings />)
  await screen.findByText('Visão geral')
  fireEvent.change(screen.getByRole('combobox', { name: 'enabled' }), { target: { value: 'true' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar Beta fechado' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
  expect(await screen.findByText(/mudou em outra sessão/)).toBeTruthy()
  expect(adminSettingsService.save).toHaveBeenCalledWith('beta', 2, true, { enabled: true })
  expect(adminSettingsService.getSettings).toHaveBeenCalledOnce()
  expect(current.values['beta.enabled']).toBe(false)
})

it('requires confirmation before granting or revoking participant access', async () => {
  adminSettingsService.getParticipants.mockResolvedValue({ items: [{ user_id: 9, username: 'alice', email: 'alice@example.test', grant_id: 44,
    active: true, expires_at: '2026-11-01T12:00:00Z', quota_seconds: 3600, consumed_seconds: '900', reserved_seconds: '0',
    available_seconds: '2700', committed_above_limit: false }], used_slots: 1, maximum: 5 })
  adminSettingsService.searchAccounts.mockResolvedValue({ items: [{ user_id: 10, username: 'bob', email: 'bob@example.test' }] })
  render(<AdminSettings />)
  await screen.findByText('alice')
  fireEvent.change(screen.getByRole('textbox', { name: 'Buscar contas' }), { target: { value: 'bob' } })
  fireEvent.click(screen.getByRole('button', { name: 'Buscar contas' }))
  expect(await screen.findByText('bob')).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Expira em'), { target: { value: '2026-11-30' } })
  fireEvent.click(await screen.findByRole('button', { name: 'Conceder acesso' }))
  expect(await screen.findByRole('dialog')).toBeTruthy()
  expect(adminSettingsService.grant).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
  expect(adminSettingsService.grant).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Conceder acesso' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
  await waitFor(() => expect(adminSettingsService.grant).toHaveBeenCalledOnce())
  expect(adminSettingsService.grant).toHaveBeenCalledWith(10, 'round-one', expect.any(String))
  expect(Number.isNaN(Date.parse(adminSettingsService.grant.mock.calls[0][2]))).toBe(false)

  fireEvent.click(await screen.findByRole('button', { name: 'Revogar acesso' }))
  expect(await screen.findByRole('dialog')).toBeTruthy()
  expect(adminSettingsService.revoke).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
  await waitFor(() => expect(adminSettingsService.revoke).toHaveBeenCalledWith(9, 44))
})
