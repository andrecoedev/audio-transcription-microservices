import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import ProviderPreferences from './ProviderPreferences'

afterEach(cleanup)

const paragraphContaining = (text) => screen.getByText((_, element) => element.tagName === 'P' && element.textContent.includes(text))

function setup(overrides = {}) {
  const settings = {
    preferences: { transcription_provider: 'automatic', intelligence_provider: 'automatic', use_diarization: false },
    providers: {
      whisper: { available: true, allowed: true, configured: true, credential_source: 'none' },
      assemblyai: { available: true, allowed: true, configured: true, credential_source: 'user' },
      gemini: { available: true, allowed: true, configured: true, credential_source: 'user' },
    },
    credentials: { assemblyai: { configured: false }, gemini: { configured: true } },
    ...overrides.settings,
  }
  const preferences = { ...settings.preferences, ...overrides.preferences }
  const updatePreference = vi.fn()
  const savePreferences = vi.fn((event) => event.preventDefault())
  render(<ProviderPreferences settings={settings} preferences={preferences} updatePreference={updatePreference}
    savePreferences={savePreferences} saving={false} />)
  return { settings, preferences, updatePreference, savePreferences }
}

it('resolves automatic transcription to local processing when there is no saved AssemblyAI key', () => {
  setup()
  expect(paragraphContaining('Transcrição local (Faster-Whisper)')).toBeTruthy()
  expect(screen.getByText(/processado localmente e não exige uma conta externa/)).toBeTruthy()
  expect(screen.getByText(/Se a transcrição falhar, não tenta outro serviço/)).toBeTruthy()
})

it('resolves automatic transcription to AssemblyAI when its own credential is configured', () => {
  setup({ settings: { credentials: { assemblyai: { configured: true } } } })
  expect(paragraphContaining('Transcrição: AssemblyAI')).toBeTruthy()
  expect(paragraphContaining('AssemblyAI usa sua própria conta e pode gerar cobranças')).toBeTruthy()
})

it('shows a configured AssemblyAI route as unavailable when credential storage makes it ineligible', () => {
  setup({
    settings: {
      credentials: { assemblyai: { configured: true } },
      providers: {
        whisper: { available: true, allowed: true, configured: true },
        assemblyai: { available: true, allowed: false, configured: false, credential_source: 'user' },
        gemini: { available: true, allowed: true, configured: true, credential_source: 'user' },
      },
    },
  })
  expect(paragraphContaining('Transcrição: AssemblyAI')).toBeTruthy()
  expect(screen.getByText('(indisponível)')).toBeTruthy()
  expect(screen.getByText(/credencial AssemblyAI salva, mas o serviço está indisponível/)).toBeTruthy()
  expect(screen.queryByText(/Transcrição: Transcrição local/)).toBeNull()
})

it('does not offer supported but disallowed services as selectable options', () => {
  setup({ settings: { providers: {
    whisper: { available: true, allowed: true, configured: true },
    assemblyai: { available: true, allowed: false, configured: false },
    gemini: { available: true, allowed: true, configured: true, credential_source: 'user' },
  } } })
  expect(screen.queryByRole('option', { name: 'AssemblyAI' })).toBeNull()
})

it('marks a saved unavailable explicit choice and blocks saving until it is changed', () => {
  const { updatePreference } = setup({
    settings: {
      preferences: { transcription_provider: 'assemblyai', intelligence_provider: 'automatic', use_diarization: false },
      providers: {
        whisper: { available: true, allowed: true, configured: true },
        assemblyai: { available: true, allowed: false, configured: false },
        gemini: { available: true, allowed: true, configured: true, credential_source: 'user' },
      },
    },
    preferences: { transcription_provider: 'assemblyai' },
  })
  expect(screen.getByRole('option', { name: 'AssemblyAI (indisponível)' }).disabled).toBe(true)
  expect(screen.getAllByText(/Conecte ou atualize a credencial em Serviços de IA/).length).toBeGreaterThan(0)
  expect(screen.getByRole('button', { name: 'Salvar preferências' }).disabled).toBe(true)
  fireEvent.change(screen.getByLabelText('Como transcrever seu áudio'), { target: { value: 'whisper' } })
  expect(updatePreference).toHaveBeenCalledWith('transcription_provider', 'whisper')
})

it('shows automatic intelligence as unavailable when Gemini has no eligible credential', () => {
  setup({ settings: { providers: {
    whisper: { available: true, allowed: true, configured: true },
    assemblyai: { available: true, allowed: true, configured: true, credential_source: 'user' },
    gemini: { available: true, allowed: false, configured: false, credential_source: null },
  }, credentials: { assemblyai: { configured: false }, gemini: { configured: false } } } })
  expect(paragraphContaining('Resumos inteligentes: Gemini')).toBeTruthy()
  expect(screen.getByText(/Gemini está indisponível para esta conta/)).toBeTruthy()
  expect(screen.queryByText(/Gemini usa sua própria conta/)).toBeNull()
})

it('explains that explicit AssemblyAI uses the USAGI quota when the platform credential is selected', () => {
  setup({
    settings: {
      preferences: { transcription_provider: 'whisper', intelligence_provider: 'automatic', use_diarization: false },
      providers: {
        whisper: { available: true, allowed: true, configured: true },
        assemblyai: { available: true, allowed: true, configured: true, credential_source: 'platform' },
        gemini: { available: true, allowed: true, configured: true, credential_source: 'platform' },
      },
    },
    preferences: { transcription_provider: 'assemblyai', intelligence_provider: 'automatic' },
  })
  expect(screen.getByText(/Se salvo, transcrição: AssemblyAI é cobrado da cota da USAGI/)).toBeTruthy()
  expect(screen.getByText(/Se salvo, resumos: Gemini é cobrado da cota da USAGI/)).toBeTruthy()
})

it('uses the configured AssemblyAI credential for automatic routing regardless of credential source metadata', () => {
  setup({ settings: {
    credentials: { assemblyai: { configured: true } },
    providers: {
      whisper: { available: true, allowed: true, configured: true },
      assemblyai: { available: true, allowed: true, configured: true, credential_source: 'platform' },
      gemini: { available: true, allowed: true, configured: true, credential_source: 'user' },
    },
  } })
  expect(paragraphContaining('Transcrição: AssemblyAI')).toBeTruthy()
  expect(paragraphContaining('AssemblyAI é cobrado da cota da USAGI')).toBeTruthy()
})

it('keeps saved active services distinct from draft selections', () => {
  setup({
    settings: {
      preferences: { transcription_provider: 'whisper', intelligence_provider: 'gemini', use_diarization: false },
    },
    preferences: { transcription_provider: 'assemblyai', intelligence_provider: 'automatic' },
  })
  expect(paragraphContaining('Transcrição local (Faster-Whisper)')).toBeTruthy()
  expect(paragraphContaining('Resumos inteligentes: Gemini')).toBeTruthy()
  expect(screen.getByText(/Rascunho: AssemblyAI para transcrição/)).toBeTruthy()
  expect(screen.getByText(/só entra em vigor depois de salva/)).toBeTruthy()
  expect(screen.getByText(/Se salvo, transcrição: AssemblyAI usa sua própria conta/)).toBeTruthy()
})

it('disables all preference controls while saving', () => {
  const settings = {
    preferences: { transcription_provider: 'automatic', intelligence_provider: 'automatic', use_diarization: false },
    providers: {
      whisper: { available: true, allowed: true, configured: true },
      assemblyai: { available: true, allowed: true, configured: true },
      gemini: { available: true, allowed: true, configured: true },
    },
  }
  render(<ProviderPreferences settings={settings} preferences={settings.preferences} updatePreference={vi.fn()}
    savePreferences={vi.fn()} saving />)
  expect(screen.getByLabelText('Como transcrever seu áudio').disabled).toBe(true)
  expect(screen.getByLabelText('Resumos inteligentes').disabled).toBe(true)
  expect(screen.getByRole('checkbox').disabled).toBe(true)
})
