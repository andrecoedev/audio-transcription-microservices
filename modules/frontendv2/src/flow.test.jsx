import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import App from './App'
import NewTranscription from './pages/NewTranscription'
import TranscriptionDetail from './pages/TranscriptionDetail'
import Transcriptions from './pages/Transcriptions'
import Meetings from './pages/Meetings'
import MeetingDetail from './pages/MeetingDetail'
import Login from './pages/Login'
import { authService } from './services/authService'
import { audioService } from './services/audioService'
import { useAuthStore } from './stores/authStore'
import toast from 'react-hot-toast'

vi.mock('./services/authService', () => ({
  authService: { getConfig: vi.fn(), me: vi.fn(), login: vi.fn() },
}))
vi.mock('./services/audioService', () => ({
  audioService: {
    checkHealth: vi.fn(),
    getProviderSettings: vi.fn(),
    updateProviderPreferences: vi.fn(),
    saveProviderCredential: vi.fn(),
    deleteProviderCredential: vi.fn(),
    getStats: vi.fn(),
    listTranscriptions: vi.fn(),
    createTranscriptionJob: vi.fn(),
    getTranscription: vi.fn(),
    deleteTranscription: vi.fn(),
    listMeetings: vi.fn(),
    getMeeting: vi.fn(),
    getMeetingTranscript: vi.fn(),
    updateMeetingTitle: vi.fn(),
    renameMeetingSpeaker: vi.fn(),
    deleteMeeting: vi.fn(),
    getMeetingActions: vi.fn(),
    getMeetingIntelligenceStatus: vi.fn(),
    getMeetingIntelligenceResult: vi.fn(),
    requestMeetingIntelligence: vi.fn(),
  },
}))
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}))

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ user: null, token: null, isAuthenticated: false })
  authService.getConfig.mockResolvedValue({ strict: true })
  audioService.getProviderSettings.mockResolvedValue({
    preferences: { transcription_provider: 'automatic', intelligence_provider: 'automatic', use_diarization: false },
    credential_storage_available: true,
    providers: {
      whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
      assemblyai: { available: true, allowed: false, configured: false, credential_source: null },
      gemini: { available: true, allowed: false, configured: false, credential_source: null },
    },
    credentials: { assemblyai: { configured: false, updated_at: null }, gemini: { configured: false, updated_at: null } },
  })
  audioService.checkHealth.mockResolvedValue({ models: {} })
  audioService.getStats.mockResolvedValue({ total_transcriptions: 0 })
  audioService.listTranscriptions.mockResolvedValue({ transcriptions: [] })
  audioService.getMeetingIntelligenceStatus.mockResolvedValue({ configured: true, generation: null, completed_revision: null })
  audioService.getMeetingActions.mockResolvedValue({ action_items: [] })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

describe('public React flow', () => {
  it('opens a durable meeting and renames its speaker', async () => {
    audioService.listMeetings.mockResolvedValue({ meetings: [{ id: 42, title: 'Reunião', created_at: '2026-09-30T00:00:00Z', duration_seconds: 3, status: 'completed', speaker_count: 1 }] })
    audioService.getMeeting.mockResolvedValue({ id: 42, title: 'Reunião', created_at: '2026-09-30T00:00:00Z', duration_seconds: 3, status: 'completed', language: 'pt', speakers: [{ id: 'SPEAKER_00', display_name: null }] })
    audioService.getMeetingTranscript.mockResolvedValue({ segments: [{ order: 0, speaker: 'SPEAKER_00', start: 0, end: 3, text: 'Olá' }] })
    audioService.renameMeetingSpeaker.mockResolvedValue({ id: 'SPEAKER_00', display_name: 'Maria' })
    render(<MemoryRouter initialEntries={['/meetings']}><Routes>
      <Route path="/meetings" element={<Meetings />} />
      <Route path="/meetings/:id" element={<MeetingDetail />} />
    </Routes></MemoryRouter>)
    fireEvent.click(await screen.findByRole('link', { name: 'Reunião' }))
    expect(await screen.findByText('Olá')).toBeTruthy()
    fireEvent.click(screen.getByText('Falantes', { selector: 'summary' }))
    fireEvent.change(screen.getByLabelText('Nome de SPEAKER_00'), { target: { value: 'Maria' } })
    fireEvent.click(screen.getByRole('button', { name: 'Renomear' }))
    await waitFor(() => expect(audioService.renameMeetingSpeaker).toHaveBeenCalledWith('42', 'SPEAKER_00', 'Maria'))
  })
  it('redirects protected routes and clears an unverified persisted session', async () => {
    localStorage.setItem('token', 'stale')
    useAuthStore.setState({ user: { name: 'Alice' }, isAuthenticated: true })
    authService.me.mockRejectedValue(Object.assign(new Error('expired'), { status: 401 }))
    window.history.pushState({}, '', '/transcriptions')
    render(<App />)
    expect(await screen.findByText('Salve e acompanhe suas reuniões')).toBeTruthy()
    expect(audioService.listTranscriptions).not.toHaveBeenCalled()
    expect(localStorage.getItem('token')).toBeNull()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })

  it('keeps authenticated route navigation available', async () => {
    localStorage.setItem('token', 'valid')
    authService.me.mockResolvedValue({
      authenticated: true,
      user: { id: 1, username: 'alice', scopes: [] },
    })
    window.history.pushState({}, '', '/new-transcription')
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Nova Transcrição' })).toBeTruthy()
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
  })

  it('logs in and persists the returned session', async () => {
    authService.login.mockResolvedValue({
      access_token: 'issued-token',
      user: { id: 1, username: 'alice', scopes: [] },
    })
    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<div>Sessão autenticada</div>} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.change(screen.getByLabelText('Usuário'), {
      target: { value: 'alice' },
    })
    fireEvent.change(screen.getByLabelText('Senha'), {
      target: { value: 'correct-password' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText('Sessão autenticada')).toBeTruthy()
    expect(authService.login).toHaveBeenCalledWith('alice', 'correct-password')
    expect(localStorage.getItem('token')).toBe('issued-token')
  })

  it('uploads through the jobs endpoint flow and opens the result route', async () => {
    audioService.createTranscriptionJob.mockResolvedValue({ id: 42 })
    render(
      <MemoryRouter initialEntries={['/new-transcription']}>
        <Routes>
          <Route path="/new-transcription" element={<NewTranscription />} />
          <Route path="/transcriptions/:id" element={<div>Resultado aberto</div>} />
        </Routes>
      </MemoryRouter>
    )
    const input = document.querySelector('input[type="file"]')
    await userEvent.upload(input, new File(['RIFFdataWAVE'], 'meeting.wav', { type: 'audio/wav' }))
    fireEvent.click(screen.getByText('Iniciar Transcrição'))
    expect(await screen.findByText('Resultado aberto')).toBeTruthy()
    expect(audioService.createTranscriptionJob).toHaveBeenCalledOnce()
    expect(audioService.createTranscriptionJob.mock.calls[0][0].name).toBe('meeting.wav')
  })

  it('sends automatic account provider selection and stored diarization preference', async () => {
    useAuthStore.setState({ user: { id: 21, registration_source: 'local' }, token: 'user-token', isAuthenticated: true })
    audioService.getProviderSettings.mockResolvedValueOnce({
      preferences: { transcription_provider: 'automatic', intelligence_provider: 'automatic', use_diarization: true },
      credential_storage_available: true,
      providers: {
        whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
        assemblyai: { available: true, allowed: true, configured: true, credential_source: 'user' },
        gemini: { available: true, allowed: true, configured: true, credential_source: 'user' },
      },
      credentials: { assemblyai: { configured: true, updated_at: null }, gemini: { configured: true, updated_at: null } },
    })
    audioService.createTranscriptionJob.mockResolvedValue({ id: 43 })
    render(<MemoryRouter><NewTranscription /></MemoryRouter>)
    const upload = document.querySelector('input[type="file"]')
    await userEvent.upload(upload, new File(['RIFFdataWAVE'], 'account.wav', { type: 'audio/wav' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Iniciar Transcrição' }))
    await waitFor(() => expect(audioService.createTranscriptionJob).toHaveBeenCalledOnce())
    expect(audioService.createTranscriptionJob.mock.calls[0][1]).toMatchObject({
      transcriptionModel: 'automatic', useDiarization: true,
    })
  })

  it('keeps an unavailable explicit preference and blocks upload until the user changes it', async () => {
    useAuthStore.setState({ user: { id: 21, registration_source: 'local' }, token: 'user-token', isAuthenticated: true })
    audioService.getProviderSettings.mockResolvedValueOnce({
      preferences: { transcription_provider: 'assemblyai', intelligence_provider: 'automatic', use_diarization: false },
      credential_storage_available: true,
      providers: {
        whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
        assemblyai: { available: true, allowed: false, configured: false, credential_source: null },
        gemini: { available: true, allowed: false, configured: false, credential_source: null },
      },
      credentials: { assemblyai: { configured: false, updated_at: null }, gemini: { configured: false, updated_at: null } },
    })
    render(<MemoryRouter><NewTranscription /></MemoryRouter>)
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: /AssemblyAI/ }).disabled).toBe(true)
    expect(screen.getByRole('button', { name: 'Iniciar Transcrição' }).disabled).toBe(true)
    await userEvent.upload(document.querySelector('input[type="file"]'), new File(['RIFFdataWAVE'], 'blocked.wav', { type: 'audio/wav' }))
    expect(screen.getByRole('button', { name: 'Iniciar Transcrição' }).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Automático' }))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByRole('button', { name: 'Iniciar Transcrição' }).disabled).toBe(false)
    expect(audioService.createTranscriptionJob).not.toHaveBeenCalled()
  })

  it('shows upload failures without navigating away', async () => {
    audioService.createTranscriptionJob.mockRejectedValue(new Error('Too many requests'))
    render(
      <MemoryRouter>
        <NewTranscription />
      </MemoryRouter>
    )
    await userEvent.upload(
      document.querySelector('input[type="file"]'),
      new File(['RIFFdataWAVE'], 'meeting.wav', { type: 'audio/wav' })
    )
    fireEvent.click(screen.getByText('Iniciar Transcrição'))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Too many requests'))
    expect(screen.getByText('Iniciar Transcrição')).toBeTruthy()
  })

  it('shows a rate-limit rejection without losing the selected file', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    audioService.createTranscriptionJob.mockRejectedValue(
      new Error('Too many requests; please retry later')
    )
    render(<MemoryRouter><NewTranscription /></MemoryRouter>)
    await userEvent.upload(
      document.querySelector('input[type="file"]'),
      new File(['RIFFdataWAVE'], 'meeting.wav', { type: 'audio/wav' })
    )
    fireEvent.click(screen.getByRole('button', { name: /Iniciar/ }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(
      'Too many requests; please retry later'
    ))
    expect(screen.getByText('meeting.wav')).toBeTruthy()
  })

  it('deletes a completed transcription and refreshes the list', async () => {
    const transcription = {
      id: 42, filename: 'meeting.wav', status: 'completed',
      created_at: '2026-09-24T00:00:00Z', duration_seconds: 3,
    }
    audioService.listTranscriptions
      .mockResolvedValueOnce({ transcriptions: [transcription] })
      .mockResolvedValue({ transcriptions: [] })
    audioService.deleteTranscription.mockResolvedValue({})
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<MemoryRouter><Transcriptions /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Excluir meeting.wav' }))
    await waitFor(() => expect(audioService.deleteTranscription).toHaveBeenCalledWith(42))
    await waitFor(() => expect(audioService.listTranscriptions).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(toast.success).toHaveBeenCalled())
  })

  it('polls a queued result until completion', async () => {
    const base = {
      id: 42,
      filename: 'meeting.wav',
      created_at: '2026-09-24T00:00:00Z',
      duration_seconds: 3,
      segments: [],
    }
    audioService.getTranscription
      .mockResolvedValueOnce({ ...base, status: 'queued' })
      .mockResolvedValue({ ...base, status: 'completed', segments: [
        { speaker: 'SPEAKER_00', start: 0, end: 1, text: 'Olá mundo' },
      ] })
    render(
      <MemoryRouter initialEntries={['/transcriptions/42']}>
        <Routes>
          <Route path="/transcriptions/:id" element={<TranscriptionDetail />} />
        </Routes>
      </MemoryRouter>
    )
    expect(await screen.findByRole('heading', { name: 'Na fila' })).toBeTruthy()
    expect(await screen.findByText('Olá mundo', {}, { timeout: 5000 })).toBeTruthy()
    expect(audioService.getTranscription).toHaveBeenCalledTimes(2)
  }, 7000)
})
