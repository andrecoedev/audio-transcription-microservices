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
  expect(paragraphContaining('Transcrição local')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Ajuda: Transcrição automática' }))
  expect(screen.getByRole('tooltip').textContent).toContain('Se houver falha, não tenta outro serviço')
})

it('resolves automatic transcription to AssemblyAI when its own credential is configured', () => {
  setup({ settings: { credentials: { assemblyai: { configured: true } } } })
  expect(paragraphContaining('Transcrição: AssemblyAI')).toBeTruthy()
  expect(paragraphContaining('Cobrança na sua conta AssemblyAI.')).toBeTruthy()
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
  expect(screen.getByText(/Sua chave AssemblyAI não está disponível para uso/)).toBeTruthy()
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
  expect(screen.getAllByText(/Confira Serviços conectados/).length).toBeGreaterThan(0)
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
  expect(screen.getByText(/Conecte ou atualize sua conta Gemini em Serviços conectados/)).toBeTruthy()
  expect(screen.queryByText(/Gemini usa sua própria conta/)).toBeNull()
})

it('offers Groq only for intelligence when the platform explicitly enables it, without changing automatic Gemini', () => {
  const { updatePreference } = setup({
    settings: { providers: {
      gemini: { available: true, allowed: true, configured: true, credential_source: 'user' },
      groq: { available: true, allowed: true, configured: true, credential_source: 'platform', platform_access: true, byok_allowed: false },
    } },
    preferences: { intelligence_provider: 'groq' },
  })

  const intelligence = screen.getByLabelText('Resumos inteligentes')
  expect(Array.from(intelligence.options).map(option => option.value)).toEqual(['automatic', 'gemini', 'groq'])
  expect(screen.getByLabelText('Como transcrever seu áudio').querySelector('option[value="groq"]')).toBeNull()
  expect(paragraphContaining('Resumos inteligentes: Gemini')).toBeTruthy()
  expect(screen.queryByText(/franquia.*Groq|Groq.*franquia/i)).toBeNull()

  fireEvent.change(intelligence, { target: { value: 'groq' } })
  expect(updatePreference).toHaveBeenCalledWith('intelligence_provider', 'groq')
  expect(screen.getByRole('status').textContent).toContain('Acesso à Groq disponibilizado pela USAGI.')
})

it('clearly disables Groq when backend platform access metadata is unavailable', () => {
  setup({
    settings: {
      preferences: { transcription_provider: 'automatic', intelligence_provider: 'groq', use_diarization: false },
      providers: {
        groq: { available: true, allowed: false, configured: false, credential_source: 'platform', platform_access: false, byok_allowed: false },
      },
    },
    preferences: { intelligence_provider: 'groq' },
  })

  expect(screen.getByRole('option', { name: 'Groq (indisponível)' }).disabled).toBe(true)
  expect(screen.getByText('Groq está indisponível para esta conta no momento.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Salvar preferências' }).disabled).toBe(true)
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
  expect(screen.getByRole('status').textContent).toContain('Usa a franquia da USAGI.')
  expect(screen.getAllByText('Usa a franquia da USAGI.')).toHaveLength(2)
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
  expect(paragraphContaining('Usa a franquia da USAGI.')).toBeTruthy()
})

it('keeps saved active services distinct from draft selections', () => {
  setup({
    settings: {
      preferences: { transcription_provider: 'whisper', intelligence_provider: 'gemini', use_diarization: false },
    },
    preferences: { transcription_provider: 'assemblyai', intelligence_provider: 'automatic' },
  })
  expect(paragraphContaining('Transcrição local')).toBeTruthy()
  expect(paragraphContaining('Resumos inteligentes: Gemini')).toBeTruthy()
  const drafts = screen.getAllByRole('status').map(element => element.textContent)
  expect(drafts.some(text => text.includes('Alteração pendente: AssemblyAI'))).toBe(true)
  expect(drafts.some(text => text.includes('Cobrança na sua conta AssemblyAI'))).toBe(true)
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
