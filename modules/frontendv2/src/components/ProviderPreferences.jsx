import { Save } from 'lucide-react'

import Button from './Button'
import HelpPopover from './HelpPopover'

const providerNames = {
  automatic: 'Automático',
  whisper: 'Transcrição local',
  assemblyai: 'AssemblyAI',
  gemini: 'Gemini',
}

function isEligible(provider) {
  return Boolean(provider?.available && provider?.allowed && provider?.configured)
}

function resolveProvider(preference, settings, kind) {
  if (preference !== 'automatic') return preference
  if (kind === 'intelligence') return 'gemini'
  return settings.credentials?.assemblyai?.configured ? 'assemblyai' : 'whisper'
}

function serviceDescription(provider, settings) {
  if (!isEligible(settings.providers?.[provider])) {
    if (provider === 'assemblyai' && settings.credentials?.assemblyai?.configured) {
      return 'Sua chave AssemblyAI não está disponível para uso. Confira Serviços conectados.'
    }
    return `Conecte ou atualize sua conta ${providerNames[provider]} em Serviços conectados.`
  }
  if (provider === 'whisper') return null
  const source = settings.providers[provider].credential_source
  if (source === 'platform') return 'Usa a franquia da USAGI.'
  if (source === 'user') return `Cobrança na sua conta ${providerNames[provider]}.`
  return null
}

function choiceLabel(provider, providers) {
  if (provider === 'automatic' || isEligible(providers[provider])) return providerNames[provider]
  return `${providerNames[provider]} (indisponível)`
}

function ProviderSelect({ kind, label, ariaLabel, savedValue, value, providers, busy, onChange }) {
  const choices = kind === 'transcription' ? ['automatic', 'whisper', 'assemblyai'] : ['automatic', 'gemini']
  const unavailableSavedChoice = value !== 'automatic' && !isEligible(providers[value]) && value === savedValue

  return <div className="text-sm font-medium text-gray-700">
    <div className="flex items-center gap-2"><label htmlFor={`preference-${kind}`}>{label}</label>
      <HelpPopover label={kind === 'transcription' ? 'Transcrição automática' : 'Resumos automáticos'}>
        {kind === 'transcription'
          ? 'Automático usa sua conta AssemblyAI quando há uma chave salva; caso contrário, usa transcrição local quando disponível. Se houver falha, não tenta outro serviço. O processamento local não envia áudio a um serviço externo.'
          : 'Automático usa Gemini nesta versão. É necessário conectar uma chave própria ou ter acesso fornecido pela USAGI.'}
      </HelpPopover></div>
    <select id={`preference-${kind}`} aria-label={ariaLabel} className="input mt-2" value={value} disabled={busy}
      onChange={(event) => onChange(event.target.value)}>
      {choices.filter((provider) => provider === 'automatic' || isEligible(providers[provider]) || provider === savedValue)
        .map((provider) => <option key={provider} value={provider} disabled={provider !== 'automatic' && !isEligible(providers[provider])}>
          {choiceLabel(provider, providers)}
        </option>)}
    </select>
    {unavailableSavedChoice && <span role="alert" className="mt-2 block text-sm text-amber-800">
      Opção salva indisponível. Confira Serviços conectados ou escolha outra opção.
    </span>}
  </div>
}

function ActiveService({ preference, kind, settings, title }) {
  const provider = resolveProvider(preference || 'automatic', settings, kind)
  const eligible = isEligible(settings.providers?.[provider])
  return <div>
    <p className="text-gray-700">{title}: <span className="font-medium">{providerNames[provider] || provider}</span>
      {!eligible && <span className="font-medium text-amber-800"> (indisponível)</span>}
    </p>
    {serviceDescription(provider, settings) && <p className="mt-1 text-gray-600">{serviceDescription(provider, settings)}</p>}
  </div>
}

export function ProviderPreferenceFields({ kind, settings, preferences, updatePreference, saving }) {
  const saved = settings.preferences || {}
  const key = kind === 'transcription' ? 'transcription_provider' : 'intelligence_provider'
  const selected = preferences?.[key] || 'automatic'
  const savedValue = saved[key] || 'automatic'
  const dirty = selected !== savedValue || (kind === 'transcription' && Boolean(preferences?.use_diarization) !== Boolean(saved.use_diarization))
  return <div className="space-y-3">
    <ProviderSelect kind={kind} label={kind === 'transcription' ? 'Como transcrever seu áudio' : 'Serviço para resumos'}
      ariaLabel={kind === 'transcription' ? 'Como transcrever seu áudio' : 'Resumos inteligentes'}
      savedValue={savedValue} value={selected} providers={settings.providers || {}} busy={saving}
      onChange={(value) => updatePreference(key, value)} />
    {kind === 'transcription' && <label className="flex items-center gap-2 text-sm text-gray-700">
      <input type="checkbox" checked={Boolean(preferences?.use_diarization)} disabled={saving}
        onChange={(event) => updatePreference('use_diarization', event.target.checked)} />
      Ativar detecção de falantes por padrão
    </label>}
    <div className="text-sm"><ActiveService title={kind === 'transcription' ? 'Transcrição' : 'Resumos inteligentes'}
      preference={savedValue} kind={kind} settings={settings} /></div>
    {dirty && <div role="status" className="rounded-lg bg-primary-50 p-3 text-sm text-primary-900">
      <p>Alteração pendente: {providerNames[selected]}.</p>
      {serviceDescription(resolveProvider(selected, settings, kind), settings) && <p className="mt-1">{serviceDescription(resolveProvider(selected, settings, kind), settings)}</p>}
    </div>}
  </div>
}

export function PreferenceSaveButton({ settings, preferences, saving }) {
  const saved = settings.preferences || {}
  const providers = settings.providers || {}
  const unavailableExplicit = ['transcription_provider', 'intelligence_provider'].some((key) => {
    const value = preferences?.[key]
    return value && value !== 'automatic' && !isEligible(providers[value])
  })
  const dirty = preferences?.transcription_provider !== saved.transcription_provider
    || preferences?.intelligence_provider !== saved.intelligence_provider
    || Boolean(preferences?.use_diarization) !== Boolean(saved.use_diarization)
  return <div className="flex flex-wrap items-center gap-3">
    <Button type="submit" icon={Save} loading={saving} disabled={saving || unavailableExplicit || !dirty}>Salvar preferências</Button>
  </div>
}

export default function ProviderPreferences(props) {
  return <form onSubmit={props.savePreferences} className="space-y-5">
    <ProviderPreferenceFields {...props} kind="transcription" />
    <ProviderPreferenceFields {...props} kind="intelligence" />
    <PreferenceSaveButton {...props} />
  </form>
}
