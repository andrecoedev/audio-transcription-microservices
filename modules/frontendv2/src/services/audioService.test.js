import { beforeEach, expect, it, vi } from 'vitest'
import api from './api'
import { audioService } from './audioService'

vi.mock('./api', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

beforeEach(() => {
  vi.clearAllMocks()
})

it('uses durable meeting endpoints for metadata, transcript and edits', async () => {
  api.get.mockResolvedValue({ data: { id: 42 } })
  api.patch.mockResolvedValue({ data: { id: 42 } })
  api.delete.mockResolvedValue({ data: {} })
  await audioService.listMeetings()
  await audioService.getMeeting(42)
  await audioService.getMeetingTranscript(42)
  await audioService.updateMeetingTitle(42, 'Título')
  await audioService.renameMeetingSpeaker(42, 'SPEAKER_00', 'Maria')
  await audioService.deleteMeeting(42)
  expect(api.get.mock.calls.map(([path]) => path)).toEqual([
    '/meetings', '/meetings/42', '/meetings/42/transcript',
  ])
  expect(api.patch).toHaveBeenCalledWith('/meetings/42', { title: 'Título' })
  expect(api.patch).toHaveBeenCalledWith('/meetings/42/speakers/SPEAKER_00', { display_name: 'Maria' })
  expect(api.delete).toHaveBeenCalledWith('/meetings/42')
})

it('uses authenticated provider-preference and credential metadata contracts', async () => {
  const metadata = { preferences: { transcription_provider: 'automatic' }, credentials: {
    assemblyai: { configured: true, updated_at: null }, gemini: { configured: false, updated_at: null },
  } }
  api.get.mockResolvedValue({ data: metadata })
  api.patch.mockResolvedValue({ data: metadata })
  api.post.mockResolvedValue({ data: metadata })
  api.delete.mockResolvedValue({ data: metadata })
  const preferences = { transcription_provider: 'automatic', intelligence_provider: 'automatic', use_diarization: true }
  await expect(audioService.getProviderSettings()).resolves.toEqual(metadata)
  await audioService.updateProviderPreferences(preferences)
  await audioService.saveProviderCredential('assemblyai', 'secret-value')
  await audioService.deleteProviderCredential('gemini')
  expect(api.get).toHaveBeenCalledWith('/settings/providers')
  expect(api.patch).toHaveBeenCalledWith('/settings/providers', { preferences })
  expect(api.post).toHaveBeenCalledWith('/settings/providers/assemblyai/credential', { secret: 'secret-value' })
  expect(api.delete).toHaveBeenCalledWith('/settings/providers/gemini/credential')
  expect(metadata.credentials.assemblyai).toEqual({ configured: true, updated_at: null })
})

it('uses only the official upload, status and result contract', async () => {
  api.post.mockResolvedValue({ data: { id: 42 } })
  api.get.mockResolvedValue({ data: { status: 'completed' } })
  const progress = vi.fn()
  const result = await audioService.createTranscriptionJob(
    new File(['RIFFdataWAVE'], 'meeting.wav', { type: 'audio/wav' }),
    { transcriptionModel: 'whisper', useDiarization: true, onUploadProgress: progress }
  )
  expect(result.id).toBe(42)
  expect(api.post.mock.calls[0][0]).toBe('/transcriptions/jobs')
  const form = api.post.mock.calls[0][1]
  expect(form.get('transcription_model')).toBe('whisper')
  expect(form.get('use_diarization')).toBe('true')
  expect(api.post.mock.calls[0][2].onUploadProgress).toBe(progress)
  await audioService.getTranscriptionJobStatus(42)
  await audioService.getTranscription(42)
  expect(api.get.mock.calls.map(([path]) => path)).toEqual([
    '/transcriptions/jobs/42/status',
    '/transcriptions/42',
  ])
  api.delete.mockResolvedValue({ data: {} })
  await audioService.deleteTranscription(42)
  expect(api.delete).toHaveBeenCalledWith('/transcriptions/42')
})
