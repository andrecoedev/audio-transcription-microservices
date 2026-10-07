import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Settings from './Settings'
import { audioService } from '../services/audioService'
import { useAuthStore } from '../stores/authStore'

vi.mock('../services/audioService', () => ({ audioService: {
  checkHealth: vi.fn(), getProviderSettings: vi.fn(), updateProviderPreferences: vi.fn(),
  saveProviderCredential: vi.fn(), deleteProviderCredential: vi.fn(),
} }))
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
  useAuthStore.setState({ user: { name: 'Pessoa', email: 'pessoa@example.test', registration_source: 'public' }, updateProfile: vi.fn() })
})
afterEach(cleanup)

describe('Settings', () => {
  it('shows accessible sections and the account-specific AI capabilities', async () => {
    renderSettings()
    expect(await screen.findByRole('heading', { name: 'Serviços de IA' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Conta' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Transcrição' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Dados e privacidade' })).toBeTruthy()
    expect(screen.getAllByText('Transcrição local (Faster-Whisper)').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Não conectado').length).toBeGreaterThan(0)
    expect(screen.getByText(/não confirma validade ou acesso/i)).toBeTruthy()
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
    const input = await screen.findByLabelText('Credencial AssemblyAI')
    fireEvent.change(input, { target: { value: 'synthetic-secret' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar credencial' }))
    await waitFor(() => expect(audioService.saveProviderCredential).toHaveBeenCalledWith('assemblyai', 'synthetic-secret'))
    await waitFor(() => expect(input.value).toBe(''))
    expect(screen.queryByText('synthetic-secret')).toBeNull()
    expect(screen.getByText('Credencial própria salva')).toBeTruthy()
    expect(screen.getByText('Gemini · Sua própria conta')).toBeTruthy()
    expect(screen.queryByText('AssemblyAI · Sua própria conta')).toBeNull()
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
    await screen.findByRole('heading', { name: 'Transcrição de áudio' })
    const transcriptionCard = screen.getByRole('heading', { name: 'Transcrição de áudio' }).closest('.card')
    expect(transcriptionCard.textContent).toContain('Não conectado')
    expect(transcriptionCard.textContent).toContain('Indisponível')
    expect(transcriptionCard.textContent).not.toContain('Faster-Whisper ativo')
  })

  it('clears unsaved provider credentials when leaving the AI services tab', async () => {
    renderSettings()
    const input = await screen.findByLabelText('Credencial AssemblyAI')
    fireEvent.change(input, { target: { value: 'temporary-secret' } })
    fireEvent.click(screen.getByRole('tab', { name: 'Conta' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Serviços de IA' }))
    expect(screen.getByLabelText('Credencial AssemblyAI').value).toBe('')
  })

  it('replaces a saved key only after explicit editing and never redisplays it', async () => {
    const saved = settings({ credentials: { assemblyai: { configured: false }, gemini: { configured: true, updated_at: '2026-10-03T12:00:00Z' } } })
    audioService.getProviderSettings.mockResolvedValue(saved)
    audioService.saveProviderCredential.mockResolvedValue(saved)
    renderSettings()
    await screen.findByText('Credencial própria salva')
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
    fireEvent.change(await screen.findByLabelText('Credencial Gemini'), { target: { value: 'not a valid key' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Salvar credencial' })[1])
    expect(await screen.findByText(/Formato da chave inválido/)).toBeTruthy()
    expect(screen.getByLabelText('Credencial Gemini').value).toBe('')
    expect(audioService.saveProviderCredential).not.toHaveBeenCalled()
  })

  it('shows safe format rejection from the API and clears rejected input', async () => {
    audioService.saveProviderCredential.mockRejectedValue(Object.assign(new Error('sensitive provider response'), { status: 422 }))
    renderSettings()
    fireEvent.change(await screen.findByLabelText('Credencial Gemini'), { target: { value: 'synthetic-rejected' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Salvar credencial' })[1])
    expect(await screen.findByText(/Formato da chave inválido/)).toBeTruthy()
    expect(screen.getByLabelText('Credencial Gemini').value).toBe('')
    expect(screen.queryByText('sensitive provider response')).toBeNull()
  })

  it('does not claim an edited preference is already active and shows failure on the transcription tab', async () => {
    audioService.updateProviderPreferences.mockRejectedValue(new Error('private detail'))
    renderSettings()
    await screen.findByLabelText('Como transcrever seu áudio')
    fireEvent.click(screen.getByRole('tab', { name: 'Transcrição' }))
    fireEvent.change(screen.getByLabelText('Como transcrever seu áudio'), { target: { value: 'whisper' } })
    expect(screen.getByText(/Rascunho:/)).toBeTruthy()
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
    expect((await screen.findAllByText(/Conexão própria indisponível/)).length).toBe(2)
    expect(screen.queryByLabelText('Credencial AssemblyAI')).toBeNull()
    expect(screen.queryByLabelText('Credencial Gemini')).toBeNull()
    expect(screen.getAllByText(/Fornecido pela USAGI está disponível/).length).toBe(2)
  })
})
