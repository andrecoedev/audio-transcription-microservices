import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Settings from './pages/Settings'
import Dashboard from './pages/Dashboard'
import Transcriptions from './pages/Transcriptions'
import Meetings from './pages/Meetings'
import TranscriptionDetail from './pages/TranscriptionDetail'
import NewTranscription from './pages/NewTranscription'
import Login from './pages/Login'
import MeetingMinutes from './pages/MeetingMinutes'
import MeetingDetail from './pages/MeetingDetail'
import { audioService } from './services/audioService'
import { guestService } from './services/guestService'
import { useAuthStore } from './stores/authStore'
import toast from 'react-hot-toast'

vi.mock('./services/audioService', () => ({ audioService: {
  checkHealth: vi.fn(), getStats: vi.fn(), listTranscriptions: vi.fn(),
  getProviderSettings: vi.fn(), updateProviderPreferences: vi.fn(),
  saveProviderCredential: vi.fn(), deleteProviderCredential: vi.fn(),
  listMeetings: vi.fn(), getTranscription: vi.fn(), getApiKeysStatus: vi.fn(),
  getMeetingMinutesStatus: vi.fn(), createTranscriptionJob: vi.fn(),
  getMeeting: vi.fn(), getMeetingTranscript: vi.fn(), getMeetingMinutes: vi.fn(),
} }))
vi.mock('./services/guestService', () => ({ guestService: { policy: vi.fn() } }))
vi.mock('./components/MeetingIntelligencePanel', () => ({ default: ({ onResultChange }) =>
  <button onClick={() => onResultChange(2)}>Simular nova revisão concluída</button> }))
vi.mock('./components/MeetingActionsPanel', () => ({ default: () => null }))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }))

beforeEach(() => {
  vi.resetAllMocks()
  guestService.policy.mockResolvedValue({ allowed_extensions: ['wav', 'mp3', 'm4a'], max_upload_mb: 100, max_audio_seconds: 600 })
  useAuthStore.setState({ user: { name: 'Teste', roles: [] } })
  audioService.checkHealth.mockResolvedValue({ database: 'connected',
    processing: { redis: 'connected', worker_available: true, worker_count: 1 },
    models: { gemini: { configured: true }, assemblyai: { configured: true } } })
  audioService.getProviderSettings.mockResolvedValue({
    preferences: { transcription_provider: 'automatic', intelligence_provider: 'automatic', use_diarization: false },
    credential_storage_available: true,
    providers: {
      whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
      assemblyai: { available: true, allowed: true, configured: true, credential_source: 'platform', byok_allowed: true },
      gemini: { available: true, allowed: true, configured: true, credential_source: 'platform', byok_allowed: true },
    },
    credentials: { assemblyai: { configured: false, updated_at: null }, gemini: { configured: false, updated_at: null } },
  })
  audioService.getStats.mockResolvedValue({})
  audioService.listTranscriptions.mockResolvedValue({ transcriptions: [], total: 0 })
  audioService.listMeetings.mockResolvedValue({ meetings: [], total: 0 })
  audioService.getMeetingMinutesStatus.mockResolvedValue({ available: false })
})
afterEach(cleanup)

describe('functional frontend contracts', () => {
  it('offers working navigation and an account area without inert information buttons', () => {
    render(<MemoryRouter><Sidebar /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'Área da conta' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Configurações' }).getAttribute('href')).toBe('/settings')
    expect(screen.getByRole('link', { name: 'Tarefas' }).getAttribute('href')).toBe('/tasks')
    expect(screen.queryByText('Modelos Ativos')).toBeNull()
    expect(screen.queryByText('Falantes', { exact: true })).toBeNull()
  })

  it('shows provider configuration for non-admins without requesting secrets/status admin APIs', async () => {
    render(<MemoryRouter><Settings /></MemoryRouter>)
    await screen.findByText('disponível')
    const provider = screen.getByText('Resumos via Gemini').parentElement
    expect(provider.textContent).toContain('configurado')
    expect(provider.textContent).not.toContain('não configurado')
    expect(audioService.getApiKeysStatus).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Verificar worker' })).toBeNull()
    expect(screen.getByText('Processamento de áudio').parentElement.textContent).toContain('disponível')
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar' }))
    await waitFor(() => expect(audioService.checkHealth).toHaveBeenCalledTimes(2))
  })

  it('saves account provider preferences and clears the transient credential field', async () => {
    const metadata = {
      preferences: { transcription_provider: 'assemblyai', intelligence_provider: 'gemini', use_diarization: true },
      credential_storage_available: true,
      providers: {
        whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
        assemblyai: { available: true, allowed: true, configured: true, credential_source: 'user', byok_allowed: true },
        gemini: { available: true, allowed: true, configured: true, credential_source: 'user', byok_allowed: true },
      },
      credentials: { assemblyai: { configured: true, updated_at: null }, gemini: { configured: false, updated_at: null } },
    }
    audioService.getProviderSettings.mockResolvedValue(metadata)
    audioService.updateProviderPreferences.mockResolvedValue(metadata)
    audioService.saveProviderCredential.mockResolvedValue(metadata)
    render(<MemoryRouter><Settings /></MemoryRouter>)
    const transcription = await screen.findByLabelText('Como transcrever seu áudio')
    fireEvent.change(transcription, { target: { value: 'whisper' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar preferências' }))
    await waitFor(() => expect(audioService.updateProviderPreferences).toHaveBeenCalledWith({
      transcription_provider: 'whisper', intelligence_provider: 'gemini', use_diarization: true,
    }))

    fireEvent.click(screen.getByRole('button', { name: 'Conectar minha API Gemini' }))
    const secretInput = screen.getByLabelText('Credencial Gemini')
    fireEvent.change(secretInput, { target: { value: 'synthetic-key-never-rendered' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Salvar credencial' })[0])
    await waitFor(() => expect(audioService.saveProviderCredential).toHaveBeenCalledWith('gemini', 'synthetic-key-never-rendered'))
    await waitFor(() => expect(secretInput.value).toBe(''))
    expect(screen.queryByText('synthetic-key-never-rendered')).toBeNull()
  })

  it('clears credential input after a failed save and shows safe error copy', async () => {
    audioService.getProviderSettings.mockResolvedValue({
      preferences: { transcription_provider: 'automatic', intelligence_provider: 'automatic', use_diarization: false },
      credential_storage_available: true,
      providers: {
        whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
        assemblyai: { available: true, allowed: false, configured: false, credential_source: null, byok_allowed: true },
        gemini: { available: true, allowed: false, configured: false, credential_source: null, byok_allowed: true },
      },
      credentials: { assemblyai: { configured: false, updated_at: null }, gemini: { configured: false, updated_at: null } },
    })
    audioService.saveProviderCredential.mockRejectedValue(new Error('provider returned sensitive detail'))
    render(<MemoryRouter><Settings /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Conectar minha API AssemblyAI' }))
    const secretInput = screen.getByLabelText('Credencial AssemblyAI')
    fireEvent.change(secretInput, { target: { value: 'synthetic-key' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Salvar credencial' })[0])
    await waitFor(() => expect(secretInput.value).toBe(''))
    expect(toast.error).toHaveBeenCalledWith('Não foi possível salvar a credencial')
    expect(toast.error).not.toHaveBeenCalledWith('provider returned sensitive detail')
  })

  it.each([
    ['assemblyai', 'transcription_provider', 'Como transcrever seu áudio'],
    ['gemini', 'intelligence_provider', 'Resumos inteligentes'],
  ])('preserves explicit %s preference after its credential is removed', async (provider, preferenceKey, label) => {
    const preferences = {
      transcription_provider: provider === 'assemblyai' ? 'assemblyai' : 'automatic',
      intelligence_provider: provider === 'gemini' ? 'gemini' : 'automatic',
      use_diarization: false,
    }
    const metadata = (credentialConfigured, allowed) => ({
      preferences,
      credential_storage_available: true,
      providers: {
        whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
        assemblyai: { available: true, allowed: provider === 'assemblyai' ? allowed : true, configured: true, credential_source: provider === 'assemblyai' && allowed ? 'user' : null, byok_allowed: provider === 'assemblyai' ? allowed : true },
        gemini: { available: true, allowed: provider === 'gemini' ? allowed : true, configured: true, credential_source: provider === 'gemini' && allowed ? 'user' : null, byok_allowed: provider === 'gemini' ? allowed : true },
      },
      credentials: {
        assemblyai: { configured: provider === 'assemblyai' ? credentialConfigured : true, updated_at: null },
        gemini: { configured: provider === 'gemini' ? credentialConfigured : true, updated_at: null },
      },
    })
    audioService.getProviderSettings.mockResolvedValue(metadata(true, true))
    audioService.deleteProviderCredential.mockResolvedValue(metadata(false, false))
    render(<MemoryRouter><Settings /></MemoryRouter>)
    const selector = await screen.findByRole('combobox', { name: label })
    expect(selector.value).toBe(provider)
    fireEvent.click(screen.getByRole('button', { name: `Remover credencial ${provider === 'assemblyai' ? 'AssemblyAI' : 'Gemini'}` }))
    expect(audioService.deleteProviderCredential).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: `Confirmar remoção ${provider === 'assemblyai' ? 'AssemblyAI' : 'Gemini'}` }))
    await waitFor(() => expect(audioService.deleteProviderCredential).toHaveBeenCalledWith(provider))
    expect(selector.value).toBe(provider)
    expect(selector.selectedOptions[0].disabled).toBe(true)
    expect(audioService.updateProviderPreferences).not.toHaveBeenCalled()
  })

  it('does not disguise dashboard failure as empty data and can retry', async () => {
    audioService.listTranscriptions.mockRejectedValueOnce(new Error('offline'))
    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByText('Nenhuma transcrição ainda.')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(await screen.findByText('Nenhuma transcrição ainda.')).toBeTruthy()
  })

  it('labels queued transcriptions honestly', async () => {
    const filename = `${'reuniao_de_planejamento_'.repeat(6)}.wav`
    audioService.listTranscriptions.mockResolvedValue({ total: 1, transcriptions: [
      { id: 1, filename, status: 'queued', created_at: '2026-10-02' },
    ] })
    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    expect(await screen.findByText('Na fila')).toBeTruthy()
    const link = screen.getByRole('link', { name: new RegExp(filename) })
    expect(link.getAttribute('href')).toBe('/transcriptions/1')
    expect(link.className).toContain('min-w-0')
    expect(link.parentElement.className).toContain('grid-cols-1')
  })

  it.each(['transcriptions', 'meetings'])('retries failed %s instead of claiming there are no records', async kind => {
    const method = kind === 'meetings' ? 'listMeetings' : 'listTranscriptions'
    audioService[method].mockRejectedValueOnce(new Error('offline'))
    render(<MemoryRouter>{kind === 'meetings' ? <Meetings /> : <Transcriptions />}</MemoryRouter>)
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByText(/Nenhuma.*ainda/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    await waitFor(() => expect(audioService[method]).toHaveBeenCalledTimes(2))
  })

  it.each(['transcriptions', 'meetings'])('makes subsequent %s pages reachable', async kind => {
    const method = kind === 'meetings' ? 'listMeetings' : 'listTranscriptions'
    const limit = kind === 'meetings' ? 20 : 10
    audioService[method].mockResolvedValue({ [kind]: [], total: limit + 1 })
    render(<MemoryRouter>{kind === 'meetings' ? <Meetings /> : <Transcriptions />}</MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Próxima' }))
    await waitFor(() => expect(audioService[method]).toHaveBeenLastCalledWith(expect.objectContaining({ skip: limit, limit })))
    expect(screen.getByRole('button', { name: 'Próxima' }).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Anterior' }))
    await waitFor(() => expect(audioService[method]).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 0 })))
  })

  it('reports failed processing and disables exports without a completed transcript', async () => {
    audioService.getTranscription.mockResolvedValue({ id: 1, filename: 'fixture.wav', status: 'failed',
      segments: null, created_at: '2026-10-02' })
    render(<MemoryRouter initialEntries={['/transcriptions/1']}><Routes>
      <Route path='/transcriptions/:id' element={<TranscriptionDetail />} />
    </Routes></MemoryRouter>)
    expect(await screen.findByRole('alert')).toBeTruthy()
    for (const name of ['Copiar', 'TXT', 'SRT']) expect(screen.getByRole('button', { name }).disabled).toBe(true)
  })

  it('reports rejected uploads instead of silently ignoring them', async () => {
    render(<MemoryRouter><NewTranscription /></MemoryRouter>)
    await screen.findByText(/Formatos disponíveis:/)
    fireEvent.drop(screen.getByText('Arraste um arquivo ou clique para selecionar').parentElement, {
      dataTransfer: { files: [new File(['x'], 'invalid.exe', { type: 'application/octet-stream' })],
        items: [{ kind: 'file', type: 'application/octet-stream', getAsFile: () => new File(['x'], 'invalid.exe', { type: 'application/octet-stream' }) }], types: ['Files'] },
    })
    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(audioService.createTranscriptionJob).not.toHaveBeenCalled()
  })

  it('associates login labels with their inputs', () => {
    render(<MemoryRouter><Login /></MemoryRouter>)
    expect(screen.getByLabelText('Usuário').getAttribute('autocomplete')).toBe('username')
    expect(screen.getByLabelText('Senha').getAttribute('autocomplete')).toBe('current-password')
  })

  it('does not send users to Settings to enter a Gemini secret', async () => {
    useAuthStore.setState({ user: { registration_source: 'public' } })
    render(<MemoryRouter><MeetingMinutes /></MemoryRouter>)
    await waitFor(() => expect(audioService.getMeetingMinutesStatus).toHaveBeenCalled())
    expect(screen.queryByText(/na página de Configurações para usar/)).toBeNull()
    expect(screen.getByText(/Geração de atas ainda não aceita uma conta Gemini conectada/i)).toBeTruthy()
    expect(screen.queryByText(/worker/i)).toBeNull()
  })

  it('refreshes reviewed minutes when a new Intelligence revision completes', async () => {
    audioService.getMeeting.mockResolvedValue({ id: 1, title: 'Fixture', speakers: [], created_at: '2026-10-02' })
    audioService.getMeetingTranscript.mockResolvedValue({ segments: [] })
    audioService.getMeetingMinutes.mockResolvedValue({ title: 'Fixture', action_items: [] })
    render(<MemoryRouter initialEntries={['/meetings/1']}><Routes>
      <Route path='/meetings/:id' element={<MeetingDetail />} />
    </Routes></MemoryRouter>)
    await waitFor(() => expect(audioService.getMeetingMinutes).toHaveBeenCalledOnce())
    fireEvent.click(screen.getByRole('button', { name: 'Simular nova revisão concluída' }))
    await waitFor(() => expect(audioService.getMeetingMinutes).toHaveBeenCalledTimes(2))
  })

  it('renders untrusted filenames as text, not HTML', async () => {
    const filename = '<img src=x onerror=alert(1)>.wav'
    audioService.listTranscriptions.mockResolvedValue({ total: 1, transcriptions: [
      { id: 1, filename, status: 'completed', created_at: '2026-10-02' },
    ] })
    const { container } = render(<MemoryRouter><Transcriptions /></MemoryRouter>)
    expect(await screen.findByText(filename)).toBeTruthy()
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('[onerror]')).toBeNull()
  })
})
