import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Settings from './Settings'
import { audioService } from '../services/audioService'
import { useAuthStore } from '../stores/authStore'
import { authService } from '../services/authService'
import { usageService } from '../services/usageService'

vi.mock('../services/audioService', () => ({ audioService: {
  checkHealth: vi.fn(), getProviderSettings: vi.fn(), updateProviderPreferences: vi.fn(),
  saveProviderCredential: vi.fn(), deleteProviderCredential: vi.fn(),
} }))
vi.mock('../services/authService', () => ({ authService: { me: vi.fn(), getConfig: vi.fn(), linkGoogle: vi.fn() } }))
vi.mock('../services/usageService', () => ({ usageService: { getOverview: vi.fn() } }))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }))

const settings = (overrides = {}) => ({
  preferences: { transcription_provider: 'automatic', intelligence_provider: 'automatic', use_diarization: false },
  credential_storage_available: true,
  providers: {
    whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
    assemblyai: { available: true, allowed: false, configured: false, credential_source: null },
    gemini: { available: true, allowed: false, configured: false, credential_source: null },
  },
  credentials: { assemblyai: { configured: false }, gemini: { configured: false } },
  ...overrides,
})
const renderSettings = () => render(<MemoryRouter><Settings /></MemoryRouter>)

beforeEach(() => {
  vi.resetAllMocks()
  audioService.checkHealth.mockResolvedValue({ database: 'connected',
    processing: { redis: 'connected', worker_available: true },
    models: { assemblyai: { configured: true }, gemini: { configured: true } },
  })
  audioService.getProviderSettings.mockResolvedValue(settings())
  authService.me.mockResolvedValue({ authenticated: true, user: { id: 17, display_name: 'Pessoa', username: 'pessoa', email: 'pessoa@example.test', auth_provider: 'local' } })
  authService.getConfig.mockResolvedValue({ firebase_enabled: false })
  usageService.getOverview.mockResolvedValue({ metrics: [] })
  useAuthStore.setState({ user: { id: 17, name: 'Pessoa', email: 'pessoa@example.test', registration_source: 'public' }, isAuthenticated: true, updateProfile: vi.fn() })
})
afterEach(cleanup)

describe('Settings', () => {
  it('discards credential drafts and capability state when the internal account changes', async () => {
    renderSettings()
    fireEvent.click(await screen.findByRole('button', { name: 'Conectar minha API AssemblyAI' }))
    fireEvent.change(screen.getByLabelText('Credencial AssemblyAI'), { target: { value: 'synthetic-transient-draft' } })
    audioService.getProviderSettings.mockImplementation(() => new Promise(() => {}))
    useAuthStore.setState({ user: { id: 9 } })
    await waitFor(() => expect(screen.queryByLabelText('Credencial AssemblyAI')).toBeNull())
    expect(audioService.saveProviderCredential).not.toHaveBeenCalled()
    expect(audioService.getProviderSettings).toHaveBeenCalledTimes(2)
    expect(screen.queryByText('synthetic-transient-draft')).toBeNull()
  })
  it('shows only the authenticated account returned for the current user id', async () => {
    authService.me.mockResolvedValueOnce({ authenticated: true, user: { id: 999, display_name: 'Outra pessoa', email: 'other@example.test' } })
    renderSettings()
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByText('Outra pessoa')).toBeNull()
    expect(authService.me).toHaveBeenCalledOnce()
  })

  it('loads usage only after the user opens the usage section', async () => {
    renderSettings()
    await screen.findByRole('heading', { name: 'Minha conta' })
    expect(usageService.getOverview).not.toHaveBeenCalled()
    fireEvent.click(screen.getAllByText('Plano e consumo')[1])
    await waitFor(() => expect(usageService.getOverview).toHaveBeenCalledOnce())
    expect(await screen.findByText('Nenhum dado de uso registrado.')).toBeTruthy()
  })

  it('shows accessible sections and the account-specific AI capabilities', async () => {
    renderSettings()
    expect(await screen.findByRole('heading', { name: 'Serviços conectados' })).toBeTruthy()
    for (const name of ['Minha conta', 'Transcrição', 'Resumos inteligentes', 'Serviços conectados']) {
      expect(screen.getByRole('heading', { name, level: 2 })).toBeTruthy()
    }
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.getAllByText('Transcrição local').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Sem credencial própria').length).toBeGreaterThan(0)
    fireEvent.focus(screen.getByRole('button', { name: 'Ajuda: AssemblyAI' }))
    expect(screen.getByRole('tooltip').textContent).toContain('criptografadas e nunca voltam à interface')
  })

  it('keeps operational health diagnostics available but collapsed by default', async () => {
    renderSettings()
    await screen.findByText('Resumos via Gemini')
    expect(screen.getByText('Processamento de áudio').parentElement.textContent).toContain('disponível')
    const diagnostics = screen.getByText('Diagnóstico do sistema').closest('details')
    expect(diagnostics.open).toBe(false)
    expect(audioService.checkHealth).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar' }))
    await waitFor(() => expect(audioService.checkHealth).toHaveBeenCalledTimes(2))
  })

  it('saves per-account preferences and displays safe inline errors', async () => {
    audioService.getProviderSettings.mockResolvedValue(settings({ preferences: {
      transcription_provider: 'automatic', intelligence_provider: 'automatic', use_diarization: false,
    } }))
    audioService.updateProviderPreferences.mockRejectedValue(new Error('sensitive detail'))
    renderSettings()
    fireEvent.change(await screen.findByLabelText('Como transcrever seu áudio'), { target: { value: 'whisper' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar preferências' }))
    await waitFor(() => expect(audioService.updateProviderPreferences).toHaveBeenCalledWith({
      transcription_provider: 'whisper', intelligence_provider: 'automatic', use_diarization: false,
    }))
    expect((await screen.findByRole('alert')).textContent).toContain('Não foi possível salvar as preferências.')
    expect(screen.queryByText('sensitive detail')).toBeNull()
  })

  it('clears a transient credential field after saving and exposes only saved status', async () => {
    const configured = settings({ credentials: { assemblyai: { configured: false }, gemini: { configured: true } },
      providers: {
        whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
        assemblyai: { available: true, allowed: false, configured: false, credential_source: null },
        gemini: { available: true, allowed: true, configured: true, credential_source: 'user' },
      } })
    audioService.getProviderSettings.mockResolvedValue(configured)
    audioService.saveProviderCredential.mockResolvedValue(configured)
    renderSettings()
    fireEvent.click(await screen.findByRole('button', { name: 'Conectar minha API AssemblyAI' }))
    const input = screen.getByLabelText('Credencial AssemblyAI')
    fireEvent.change(input, { target: { value: 'synthetic-secret' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar credencial' }))
    await waitFor(() => expect(audioService.saveProviderCredential).toHaveBeenCalledWith('assemblyai', 'synthetic-secret'))
    await waitFor(() => expect(input.value).toBe(''))
    expect(screen.queryByText('synthetic-secret')).toBeNull()
    expect(screen.getByText('Credencial salva')).toBeTruthy()
    expect(screen.getAllByText(/Cobrança na sua conta Gemini/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Cobrança na sua conta AssemblyAI/).length).toBeGreaterThan(0)
  })

  it('does not claim any transcription provider is active when the account has none', async () => {
    audioService.getProviderSettings.mockResolvedValue(settings({
      providers: {
        whisper: { available: true, allowed: false, configured: false, credential_source: 'none' },
        assemblyai: { available: true, allowed: false, configured: false, credential_source: null },
        gemini: { available: true, allowed: false, configured: false, credential_source: null },
      },
    }))
    renderSettings()
    await screen.findByRole('heading', { name: 'AssemblyAI' })
    const transcriptionCard = screen.getByRole('heading', { name: 'AssemblyAI' }).closest('.card')
    expect(transcriptionCard.textContent).toContain('Sem credencial própria')
    expect(transcriptionCard.textContent).toContain('não habilitado para esta conta')
    expect(transcriptionCard.textContent).not.toContain('Faster-Whisper ativo')
  })

  it('clears unsaved provider credentials when refreshing settings', async () => {
    renderSettings()
    fireEvent.click(await screen.findByRole('button', { name: 'Conectar minha API AssemblyAI' }))
    const input = screen.getByLabelText('Credencial AssemblyAI')
    fireEvent.change(input, { target: { value: 'temporary-secret' } })
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar' }))
    await waitFor(() => expect(screen.getByLabelText('Credencial AssemblyAI').value).toBe(''))
  })

  it('replaces a saved key only after explicit editing and never redisplays it', async () => {
    const saved = settings({ credentials: { assemblyai: { configured: false }, gemini: { configured: true, updated_at: '2026-10-03T12:00:00Z' } } })
    audioService.getProviderSettings.mockResolvedValue(saved)
    audioService.saveProviderCredential.mockResolvedValue(saved)
    renderSettings()
    await screen.findByText('Credencial salva')
    expect(screen.queryByLabelText('Credencial Gemini')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Substituir chave Gemini' }))
    fireEvent.change(screen.getByLabelText('Credencial Gemini'), { target: { value: 'synthetic-replacement' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar nova chave' }))
    await waitFor(() => expect(audioService.saveProviderCredential).toHaveBeenCalledWith('gemini', 'synthetic-replacement'))
    await waitFor(() => expect(screen.queryByLabelText('Credencial Gemini')).toBeNull())
    expect(screen.queryByText('synthetic-replacement')).toBeNull()
  })

  it('cancels removal without issuing a request', async () => {
    audioService.getProviderSettings.mockResolvedValue(settings({ credentials: { assemblyai: { configured: false }, gemini: { configured: true } } }))
    renderSettings()
    fireEvent.click(await screen.findByRole('button', { name: 'Remover credencial Gemini' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar remoção' }))
    expect(audioService.deleteProviderCredential).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Confirmar remoção Gemini' })).toBeNull()
  })

  it('rejects malformed input without requesting external validation or exposing the key', async () => {
    renderSettings()
    fireEvent.click(await screen.findByRole('button', { name: 'Conectar minha API Gemini' }))
    fireEvent.change(screen.getByLabelText('Credencial Gemini'), { target: { value: 'not a valid key' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar credencial' }))
    expect(await screen.findByText(/Formato da chave inválido/)).toBeTruthy()
    expect(screen.getByLabelText('Credencial Gemini').value).toBe('')
    expect(audioService.saveProviderCredential).not.toHaveBeenCalled()
  })

  it('shows safe format rejection from the API and clears rejected input', async () => {
    audioService.saveProviderCredential.mockRejectedValue(Object.assign(new Error('sensitive provider response'), { status: 422 }))
    renderSettings()
    fireEvent.click(await screen.findByRole('button', { name: 'Conectar minha API Gemini' }))
    fireEvent.change(screen.getByLabelText('Credencial Gemini'), { target: { value: 'synthetic-rejected' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar credencial' }))
    expect(await screen.findByText(/Formato da chave inválido/)).toBeTruthy()
    expect(screen.getByLabelText('Credencial Gemini').value).toBe('')
    expect(screen.queryByText('sensitive provider response')).toBeNull()
  })

  it('does not claim an edited preference is already active and shows failure on the single page', async () => {
    audioService.updateProviderPreferences.mockRejectedValue(new Error('private detail'))
    renderSettings()
    await screen.findByLabelText('Como transcrever seu áudio')
    fireEvent.change(screen.getByLabelText('Como transcrever seu áudio'), { target: { value: 'whisper' } })
    expect(screen.getByText(/Alteração pendente:/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Salvar preferências' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Não foi possível salvar as preferências')
    expect(screen.queryByText('private detail')).toBeNull()
  })

  it('explains unavailable BYOK storage even when the platform service is allowed', async () => {
    audioService.getProviderSettings.mockResolvedValue(settings({ credential_storage_available: false,
      providers: {
        whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
        assemblyai: { available: true, allowed: true, configured: true, credential_source: 'platform' },
        gemini: { available: true, allowed: true, configured: true, credential_source: 'platform' },
      } }))
    renderSettings()
    expect((await screen.findAllByText(/Não é possível conectar uma chave agora/)).length).toBe(2)
    expect(screen.queryByLabelText('Credencial AssemblyAI')).toBeNull()
    expect(screen.queryByLabelText('Credencial Gemini')).toBeNull()
    expect(screen.getAllByText('habilitado').length).toBe(2)
  })
})
