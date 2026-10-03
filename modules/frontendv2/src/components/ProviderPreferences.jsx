import { Save } from 'lucide-react'

import Button from './Button'

const providerNames = {
  automatic: 'Automático',
  whisper: 'Transcrição local (Faster-Whisper)',
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
      return 'Há uma credencial AssemblyAI salva, mas o serviço está indisponível. Verifique o armazenamento ou conecte novamente sua conta. Automático não tenta outro serviço se houver falha.'
    }
    return `${providerNames[provider]} está indisponível para esta conta. Conecte ou atualize a credencial em Serviços de IA.`
  }
  if (provider === 'whisper') return 'O áudio é processado localmente e não exige uma conta externa.'
  const source = settings.providers[provider].credential_source
  if (source === 'platform') return `${providerNames[provider]} é cobrado da cota da USAGI. Fornecido pela USAGI: utiliza a franquia/créditos disponíveis na USAGI. Não há informação de saldo disponível aqui.`
  if (source === 'user') return `${providerNames[provider]} usa sua própria conta e pode gerar cobranças conforme o uso.`
  return `${providerNames[provider]} está disponível.`
}

function choiceLabel(provider, providers) {
  if (provider === 'automatic' || isEligible(providers[provider])) return providerNames[provider]
  return `${providerNames[provider]} (indisponível)`
}

function ProviderSelect({ kind, label, ariaLabel, savedValue, value, providers, busy, onChange }) {
  const choices = kind === 'transcription' ? ['automatic', 'whisper', 'assemblyai'] : ['automatic', 'gemini']
  const unavailableSavedChoice = value !== 'automatic' && !isEligible(providers[value]) && value === savedValue

  return <label className="block text-sm font-medium text-gray-700">
    {label}
    <select aria-label={ariaLabel} className="input mt-2" value={value} disabled={busy}
      onChange={(event) => onChange(event.target.value)}>
      {choices.filter((provider) => provider === 'automatic' || isEligible(providers[provider]) || provider === savedValue)
        .map((provider) => <option key={provider} value={provider} disabled={provider !== 'automatic' && !isEligible(providers[provider])}>
          {choiceLabel(provider, providers)}
        </option>)}
    </select>
    {unavailableSavedChoice && <span role="alert" className="mt-2 block text-sm text-amber-800">
      Esta opção salva está indisponível. Conecte ou atualize a credencial em Serviços de IA, ou escolha Automático.
    </span>}
  </label>
}

function ActiveService({ preference, kind, settings, title }) {
  const provider = resolveProvider(preference || 'automatic', settings, kind)
  const eligible = isEligible(settings.providers?.[provider])
  return <div>
    <p className="text-gray-700">{title}: <span className="font-medium">{providerNames[provider] || provider}</span>
      {!eligible && <span className="font-medium text-amber-800"> (indisponível)</span>}
    </p>
    <p className="mt-1 text-gray-600">{serviceDescription(provider, settings)}</p>
  </div>
}

export default function ProviderPreferences({ settings, preferences, updatePreference, savePreferences, saving }) {
  const saved = settings.preferences || {}
  const providers = settings.providers || {}
  const unavailableExplicit = ['transcription_provider', 'intelligence_provider'].some((key) => {
    const value = preferences?.[key]
    return value && value !== 'automatic' && !isEligible(providers[value])
  })
  const dirty = preferences?.transcription_provider !== saved.transcription_provider
    || preferences?.intelligence_provider !== saved.intelligence_provider
    || Boolean(preferences?.use_diarization) !== Boolean(saved.use_diarization)
  const savedTranscription = saved.transcription_provider || 'automatic'
  const savedIntelligence = saved.intelligence_provider || 'automatic'
  const draftTranscription = preferences?.transcription_provider || 'automatic'
  const draftIntelligence = preferences?.intelligence_provider || 'automatic'

  return <form onSubmit={savePreferences} className="rounded-lg border border-gray-200 bg-white p-5">
    <h3 className="mb-2 text-lg font-semibold text-gray-900">Como seu áudio será processado</h3>
    <p className="mb-4 text-sm text-gray-600">O serviço selecionado reflete as configurações salvas, não um teste de conexão. Alterações ficam como rascunho até serem salvas.</p>
    <div className="mb-4 space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm">
      <p className="font-medium text-gray-900">Ativo nas configurações salvas</p>
      <ActiveService title="Transcrição" preference={savedTranscription} kind="transcription" settings={settings} />
      <ActiveService title="Resumos inteligentes" preference={savedIntelligence} kind="intelligence" settings={settings} />
      {savedTranscription === 'automatic' && <p className="text-gray-600">Automático escolhe um serviço antes de iniciar. Se a transcrição falhar, não tenta outro serviço.</p>}
      <p className="text-gray-600">Automático: usa sua conta AssemblyAI se houver uma chave salva; caso contrário, usa processamento local quando disponível. Para resumos, usa Gemini, o único serviço suportado nesta versão.</p>
    </div>
    <fieldset disabled={saving} className="grid gap-4 md:grid-cols-2">
      <ProviderSelect kind="transcription" label="Como transcrever seu áudio" ariaLabel="Provedor de transcrição"
        savedValue={savedTranscription} value={draftTranscription} providers={providers} busy={saving}
        onChange={(value) => updatePreference('transcription_provider', value)} />
      <ProviderSelect kind="intelligence" label="Resumos inteligentes" ariaLabel="Provedor de inteligência de reuniões"
        savedValue={savedIntelligence} value={draftIntelligence} providers={providers} busy={saving}
        onChange={(value) => updatePreference('intelligence_provider', value)} />
      <label className="flex items-center gap-2 text-sm text-gray-700 md:col-span-2">
        <input type="checkbox" checked={Boolean(preferences?.use_diarization)} disabled={saving}
          onChange={(event) => updatePreference('use_diarization', event.target.checked)} />
        Ativar detecção de falantes por padrão
      </label>
    </fieldset>
    {dirty && <>
      <p className="mt-3 text-sm text-gray-600">Rascunho: {providerNames[draftTranscription]} para transcrição e {providerNames[draftIntelligence]} para resumos. A alteração só entra em vigor depois de salva.</p>
      <div className="mt-2 space-y-1 text-sm text-gray-600">
        <p>Se salvo, transcrição: {serviceDescription(resolveProvider(draftTranscription, settings, 'transcription'), settings)}</p>
        <p>Se salvo, resumos: {serviceDescription(resolveProvider(draftIntelligence, settings, 'intelligence'), settings)}</p>
      </div>
    </>}
    <div className="mt-4"><Button type="submit" icon={Save} loading={saving} disabled={saving || unavailableExplicit || !dirty}>Salvar preferências</Button></div>
  </form>
}
