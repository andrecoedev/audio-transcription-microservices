import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
    financial: { authorized_usd: '0', available_usd: '0', committed_above_limit: false, alert_reached: false, review_required: false, balance_review_valid: true, price_review_valid: true, unresolved_calls: 0, queued_calls: 0 },
    system: { database: 'connected', assemblyai_credential_configured: true, firebase_configured: true } })
  adminSettingsService.getParticipants.mockResolvedValue({ items: [], used_slots: 0, maximum: 5 })
  adminSettingsService.getHistory.mockResolvedValue({ items: [] })
})
afterEach(cleanup)

it('loads the settings, keeps model fixed, and shows credential configuration without provider checks', async () => {
  render(<AdminSettings />)
  expect(await screen.findByText('Universal-3.5 Pro')).toBeTruthy()
  expect(screen.getByText('Configurada')).toBeTruthy()
  expect(screen.getByText('Conectado')).toBeTruthy()
  expect(screen.getByText('Uso autorizado estimado').parentElement.textContent).toContain('US$')
  expect(screen.getByText('Estado da rodada Beta').parentElement.textContent).toContain('Desativada')
  expect(document.querySelectorAll('.card')).toHaveLength(4)
  expect(screen.queryByText('universal-3-5-pro')).toBeNull()
  expect(adminSettingsService.getSettings).toHaveBeenCalledOnce()
})

it('shows loading and an actionable safe error when the first load fails', async () => {
  adminSettingsService.getSettings.mockRejectedValueOnce(new Error('Não foi possível carregar as configurações administrativas.'))
  render(<AdminSettings />)
  expect(screen.getByRole('status').textContent).toContain('Carregando')
  expect((await screen.findByRole('alert')).textContent).toContain('Não foi possível carregar as configurações administrativas.')
})

it('shows unprepared policy text that preserves existing financial and round history', async () => {
  adminSettingsService.getSettings.mockResolvedValueOnce({ ...settings(), configured: false })
  render(<AdminSettings />)
  await screen.findByText('Configuração ainda não preparada')
  fireEvent.click(screen.getByRole('button', { name: 'Preparar configuração' }))
  expect((await screen.findByRole('dialog')).textContent).toContain('preserva a rodada, o orçamento e o histórico já existentes')
  expect(adminSettingsService.initialize).not.toHaveBeenCalled()
})

it('announces missing operational reviews without exposing a provider balance', async () => {
  adminSettingsService.getOverview.mockResolvedValueOnce({
    participants_used: 0, participants_maximum: 5, consumed_seconds: '0', reserved_seconds: '0',
    financial: { authorized_usd: '0.00000001', available_usd: '0', committed_above_limit: false, alert_reached: false,
      review_required: false, balance_review_valid: false, price_review_valid: false, unresolved_calls: 0, queued_calls: 0 },
    system: { database: 'connected', assemblyai_credential_configured: false, firebase_configured: false },
  })
  render(<AdminSettings />)
  expect(await screen.findByText(/Confira a autorização operacional do orçamento e a tarifa registrada/)).toBeTruthy()
  expect(screen.getByText('Uso autorizado estimado').parentElement.textContent).toContain('0,00000001')
  expect(screen.queryByText(/saldo externo:/i)).toBeNull()
})

it('requires explicit confirmation for activation and leaves the draft unchanged when canceled', async () => {
  render(<AdminSettings />)
  await screen.findByText('Visão geral')
  fireEvent.change(screen.getByRole('combobox', { name: 'Ativação da rodada' }), { target: { value: 'true' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar Beta fechado' }))
  expect(await screen.findByRole('dialog')).toBeTruthy()
  expect(adminSettingsService.save).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(adminSettingsService.save).not.toHaveBeenCalled()
})

it('traps focus in the confirmation dialog and restores it after Escape', async () => {
  const user = userEvent.setup()
  render(<AdminSettings />)
  await screen.findByText('Visão geral')
  const opener = screen.getByRole('button', { name: 'Salvar Beta fechado' })
  await user.selectOptions(screen.getByRole('combobox', { name: 'Ativação da rodada' }), 'true')
  await user.click(opener)
  expect(await screen.findByRole('dialog')).toBeTruthy()
  const cancel = screen.getByRole('button', { name: 'Cancelar' })
  const confirm = screen.getByRole('button', { name: 'Confirmar' })
  expect(document.activeElement).toBe(cancel)
  await user.tab()
  expect(document.activeElement).toBe(confirm)
  await user.tab()
  expect(document.activeElement).toBe(cancel)
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(opener)
})

it('saves an activation only after confirmation', async () => {
  adminSettingsService.save.mockResolvedValue(settings({ 'beta.enabled': true }))
  render(<AdminSettings />)
  await screen.findByText('Visão geral')
  fireEvent.change(screen.getByRole('combobox', { name: 'Ativação da rodada' }), { target: { value: 'true' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar Beta fechado' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
  expect(await screen.findByText('Alteração salva.')).toBeTruthy()
  expect(adminSettingsService.save).toHaveBeenCalledWith('beta', 2, true, { enabled: true })
})

it('disables reload and other confirmation or write actions while a save is pending', async () => {
  let finishSave
  adminSettingsService.save.mockImplementationOnce(() => new Promise((resolve) => { finishSave = resolve }))
  const user = userEvent.setup()
  render(<AdminSettings />)
  await screen.findByText('Visão geral')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Ativação da rodada' }), 'true')
  await user.click(screen.getByRole('button', { name: 'Salvar Beta fechado' }))
  await user.click(await screen.findByRole('button', { name: 'Confirmar' }))
  expect(screen.getByRole('button', { name: 'Recarregar' }).disabled).toBe(true)
  expect(screen.getByRole('button', { name: 'Salvar Limites' }).disabled).toBe(true)
  expect(screen.getByRole('button', { name: 'Cancelar' }).disabled).toBe(true)
  expect(screen.getByRole('dialog').querySelectorAll('button')[1].disabled).toBe(true)
  finishSave(settings({ 'beta.enabled': true }))
  expect(await screen.findByText('Alteração salva.')).toBeTruthy()
})

it('preserves dirty fields in another section when one section is saved', async () => {
  adminSettingsService.save.mockResolvedValueOnce(settings({ 'beta.round_name': 'Nova rodada' }))
  render(<AdminSettings />)
  await screen.findByText('Visão geral')
  fireEvent.change(screen.getByRole('textbox', { name: 'Nome da rodada' }), { target: { value: 'Nova rodada' } })
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Tamanho máximo por arquivo (MB)' }), { target: { value: '80' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar Beta fechado' }))
  await screen.findByText('Alteração salva.')
  expect(screen.getByRole('spinbutton', { name: 'Tamanho máximo por arquivo (MB)' }).value).toBe('80')
  expect(screen.getByRole('button', { name: 'Salvar Limites' }).disabled).toBe(false)
})

it('keeps a draft after a version conflict and saves only after explicit confirmation', async () => {
  const current = settings()
  adminSettingsService.save.mockRejectedValueOnce(Object.assign(new Error('conflict'), { status: 409, code: 'admin_settings_revision_conflict' }))
  render(<AdminSettings />)
  await screen.findByText('Visão geral')
  fireEvent.change(screen.getByRole('combobox', { name: 'Ativação da rodada' }), { target: { value: 'true' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar Beta fechado' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
  expect(await screen.findByText(/mudou em outra sessão/)).toBeTruthy()
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(adminSettingsService.save).toHaveBeenCalledWith('beta', 2, true, { enabled: true })
  expect(adminSettingsService.getSettings).toHaveBeenCalledOnce()
  expect(current.values['beta.enabled']).toBe(false)
  expect(screen.getByRole('combobox', { name: 'Ativação da rodada' }).value).toBe('true')
})

it('shows the operational conflict without suggesting draft loss or another-session changes', async () => {
  adminSettingsService.save.mockRejectedValueOnce(Object.assign(new Error('O limite de participantes não pode ficar abaixo das vagas já utilizadas nesta rodada.'), { status: 409 }))
  render(<AdminSettings />)
  await screen.findByText('Visão geral')
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Limite de participantes (contas)' }), { target: { value: '1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar Beta fechado' }))
  expect(await screen.findByText(/limite de participantes não pode/)).toBeTruthy()
  expect(screen.queryByText(/mudou em outra sessão/)).toBeNull()
  expect(screen.queryByRole('button', { name: 'Recarregar e descartar rascunho' })).toBeNull()
})

it('shows who changed a setting and its previous and new values in history', async () => {
  adminSettingsService.getHistory.mockResolvedValue({ items: [{ id: 1, event: 'admin.settings_changed',
    actor_user_id: 7, created_at: '2026-10-15T12:00:00Z', changes: { version: 2,
      before: { 'assemblyai.hard_stop_usd': '15' }, after: { 'assemblyai.hard_stop_usd': '25' } } }] })
  render(<AdminSettings />)
  fireEvent.click(await screen.findByText('Histórico de alterações (1)'))
  expect(screen.getByText(/Administrador 7/)).toBeTruthy()
  expect(screen.getByText(/Teto interno.*15.*25/)).toBeTruthy()
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
