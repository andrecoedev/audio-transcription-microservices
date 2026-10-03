import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Save, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'

import Button from '../components/Button'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import PageHeader from '../components/PageHeader'
import { audioService } from '../services/audioService'
import { useAuthStore } from '../stores/authStore'

const tabs = [
  { id: 'account', label: 'Conta' },
  { id: 'transcription', label: 'Transcrição' },
  { id: 'ai', label: 'Serviços de IA' },
  { id: 'privacy', label: 'Dados e privacidade' },
]

export default function Settings() {
  const user = useAuthStore((state) => state.user)
  const updateProfile = useAuthStore((state) => state.updateProfile)
  const [activeTab, setActiveTab] = useState('ai')
  const [providerSettings, setProviderSettings] = useState(null)
  const [health, setHealth] = useState(null)
  const [statusError, setStatusError] = useState(false)
  const [statusLoading, setStatusLoading] = useState(false)
  const [providerError, setProviderError] = useState(false)
  const [providerLoading, setProviderLoading] = useState(true)
  const [providerSaving, setProviderSaving] = useState(false)
  const [credentials, setCredentials] = useState({ assemblyai: '', gemini: '' })
  const [profile, setProfile] = useState({ name: user?.name || '', email: user?.email || '' })
  const [errorMessage, setErrorMessage] = useState('')

  const refreshProviderSettings = useCallback(async () => {
    setProviderLoading(true)
    setErrorMessage('')
    try {
      setProviderSettings(await audioService.getProviderSettings())
      setProviderError(false)
    } catch {
      setProviderSettings(null)
      setProviderError(true)
    } finally {
      setProviderLoading(false)
    }
  }, [])

  const refreshStatus = useCallback(async () => {
    setStatusLoading(true)
    setStatusError(false)
    try {
      setHealth(await audioService.checkHealth())
    } catch {
      setHealth(null)
      setStatusError(true)
    } finally {
      setStatusLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshProviderSettings()
    refreshStatus()
  }, [refreshProviderSettings, refreshStatus])

  const updatePreference = (key, value) => setProviderSettings((current) => ({
    ...current,
    preferences: { ...current.preferences, [key]: value },
  }))

  const savePreferences = async (event) => {
    event.preventDefault()
    setProviderSaving(true)
    setErrorMessage('')
    try {
      setProviderSettings(await audioService.updateProviderPreferences(providerSettings.preferences))
      toast.success('Preferências de provedores salvas')
    } catch {
      setErrorMessage('Não foi possível salvar as preferências. Tente novamente.')
      toast.error('Não foi possível salvar as preferências de provedores')
    } finally {
      setProviderSaving(false)
    }
  }

  const saveCredential = async (provider) => {
    const secret = credentials[provider]
    if (!secret) return
    setProviderSaving(true)
    setErrorMessage('')
    try {
      setProviderSettings(await audioService.saveProviderCredential(provider, secret))
      toast.success('Credencial salva')
    } catch {
      setErrorMessage('Não foi possível salvar a credencial. Confira os dados e tente novamente.')
      toast.error('Não foi possível salvar a credencial')
    } finally {
      setCredentials((current) => ({ ...current, [provider]: '' }))
      setProviderSaving(false)
    }
  }

  const removeCredential = async (provider) => {
    setProviderSaving(true)
    setErrorMessage('')
    try {
      setProviderSettings(await audioService.deleteProviderCredential(provider))
      toast.success('Credencial removida')
    } catch {
      setErrorMessage('Não foi possível remover a credencial. Tente novamente.')
      toast.error('Não foi possível remover a credencial')
    } finally {
      setCredentials((current) => ({ ...current, [provider]: '' }))
      setProviderSaving(false)
    }
  }

  const saveProfileLocally = () => {
    updateProfile(profile)
    toast.success('Preferências locais atualizadas')
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader title="Configurações" description="Gerencie preferências, serviços de IA e credenciais da sua conta.">
        <Button variant="outline" size="sm" onClick={refreshStatus} loading={statusLoading} disabled={statusLoading} icon={RefreshCw}>Atualizar</Button>
      </PageHeader>

      <div role="tablist" aria-label="Seções das configurações" className="flex flex-wrap gap-2">
        {tabs.map((tab) => <button key={tab.id} id={`settings-tab-${tab.id}`} type="button" role="tab"
          aria-selected={activeTab === tab.id} aria-controls={`settings-panel-${tab.id}`}
          onClick={() => {
            setCredentials({ assemblyai: '', gemini: '' })
            setActiveTab(tab.id)
          }}
          className={`rounded-full border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${activeTab === tab.id ? 'border-primary-100 bg-primary-50 font-semibold text-primary-800' : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'}`}>
          {tab.label}
        </button>)}
      </div>

      <section role="tabpanel" id={`settings-panel-${activeTab}`} aria-labelledby={`settings-tab-${activeTab}`}>
        {activeTab === 'account' && <Card>
          <CardHeader><CardTitle>Conta</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <label className="block text-sm font-medium text-gray-700">Nome
              <input value={profile.name} onChange={(event) => setProfile({ ...profile, name: event.target.value })} className="input mt-2" />
            </label>
            <label className="block text-sm font-medium text-gray-700">E-mail
              <input type="email" value={profile.email} onChange={(event) => setProfile({ ...profile, email: event.target.value })} className="input mt-2" />
            </label>
            <Button onClick={saveProfileLocally} icon={Save}>Salvar preferências locais</Button>
            <p className="text-sm text-gray-500">Nome e e-mail são preferências deste navegador e não alteram os dados de acesso da conta.</p>
          </CardContent>
        </Card>}

        {activeTab === 'transcription' && <Card>
          <CardHeader><CardTitle>Preferências de transcrição</CardTitle></CardHeader>
          <CardContent>{providerSettings ? <PreferencesForm settings={providerSettings} updatePreference={updatePreference}
            savePreferences={savePreferences} providerSaving={providerSaving} /> : <LoadingState loading={providerLoading} error={providerError} retry={refreshProviderSettings} />}</CardContent>
        </Card>}

        {activeTab === 'ai' && <div className="space-y-6">
          {providerLoading && <p role="status" className="text-gray-600">Carregando serviços da sua conta…</p>}
          {providerError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">Não foi possível carregar os serviços de IA.
            <Button variant="outline" className="ml-3" onClick={refreshProviderSettings}>Tentar novamente</Button>
          </div>}
          {providerSettings && <>
            <div>
              <h2 className="text-2xl font-semibold text-gray-900">Serviços de IA</h2>
              <p className="mt-1 text-gray-600">As opções disponíveis refletem as permissões e credenciais desta conta.</p>
            </div>
            {errorMessage && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{errorMessage}</p>}
            <div className="grid gap-4 lg:grid-cols-2">
              <ProviderCard title="Transcrição de áudio" provider="assemblyai" configuredProvider={providerSettings.providers.assemblyai}
                credential={providerSettings.credentials.assemblyai} settings={providerSettings} saving={providerSaving}
                value={credentials.assemblyai} onChange={(value) => setCredentials({ ...credentials, assemblyai: value })}
                onSave={() => saveCredential('assemblyai')} onRemove={() => removeCredential('assemblyai')} />
              <ProviderCard title="Resumos inteligentes" provider="gemini" configuredProvider={providerSettings.providers.gemini}
                credential={providerSettings.credentials.gemini} settings={providerSettings} saving={providerSaving}
                value={credentials.gemini} onChange={(value) => setCredentials({ ...credentials, gemini: value })}
                onSave={() => saveCredential('gemini')} onRemove={() => removeCredential('gemini')} />
            </div>
            <PreferencesForm settings={providerSettings} updatePreference={updatePreference}
              savePreferences={savePreferences} providerSaving={providerSaving} />
            <div className="flex gap-3 rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-600">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary-800" />
              <p><span className="font-medium text-gray-900">Credenciais protegidas.</span> Depois de salvas, as chaves não são exibidas novamente. “Configurada” indica que foi salva; não confirma validade ou acesso no serviço externo.</p>
            </div>
            <details className="rounded-lg border border-gray-200 bg-white p-4">
              <summary className="cursor-pointer font-medium text-gray-900">Diagnóstico do sistema</summary>
              <div className="mt-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <p className="text-sm text-gray-600">Estado reportado pelos serviços da USAGI.</p>
                </div>
                {statusError && <p role="alert" className="mb-2 text-sm text-red-700">Não foi possível consultar o sistema. Tente novamente.</p>}
                <div className="space-y-2 text-sm">
                  <StatusRow label="Banco" value={health?.database || 'não verificado'} />
                  <StatusRow label="Redis" value={health?.processing?.redis || 'não verificado'} />
                  <StatusRow label="Worker RQ" value={health?.processing
                    ? health.processing.worker_available ? 'disponível' : 'indisponível' : 'não verificado'} />
                  {[
                    ['Faster-Whisper local', 'whisper'], ['Pyannote local', 'diarization'],
                    ['AssemblyAI externo', 'assemblyai'], ['Gemini externo', 'gemini'],
                  ].map(([label, provider]) => <StatusRow key={provider} label={label} value={
                    health?.models?.[provider] ? health.models[provider].configured ? 'configurado' : 'não configurado' : 'não verificado'
                  } />)}
                </div>
                <p className="mt-3 text-xs text-gray-500">Configuração reportada não comprova carregamento dos modelos nem disponibilidade de APIs externas.</p>
                <p className="mt-3 text-sm"><Link to="/meeting-minutes" className="font-medium text-primary-800 hover:underline">Abrir atas de reunião</Link></p>
              </div>
            </details>
          </>}
        </div>}

        {activeTab === 'privacy' && <Card>
          <CardHeader><CardTitle>Dados e privacidade</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm text-gray-600">
            <p>As transcrições da conta ficam associadas à sua identidade e aparecem no histórico autenticado.</p>
            <p>Credenciais próprias são guardadas de forma protegida no serviço e nunca são retornadas à interface após o salvamento.</p>
            <p>Remover uma credencial da USAGI não a revoga no serviço externo. Para revogá-la, use também as configurações da sua conta nesse serviço.</p>
            <p>Esta versão não oferece exclusão de conta ou exportação de dados pessoais nesta tela.</p>
          </CardContent>
        </Card>}
      </section>
    </div>
  )
}

function PreferencesForm({ settings, updatePreference, savePreferences, providerSaving }) {
  const { preferences, providers } = settings
  const label = (provider) => providers[provider].allowed ? provider === 'whisper' ? 'Faster-Whisper' : provider === 'assemblyai' ? 'AssemblyAI' : 'Gemini' : `${provider === 'assemblyai' ? 'AssemblyAI' : provider === 'gemini' ? 'Gemini' : 'Faster-Whisper'} (indisponível nesta conta)`
  return <form onSubmit={savePreferences} className="rounded-lg border border-gray-200 bg-white p-5">
    <h3 className="mb-4 text-lg font-semibold text-gray-900">Preferências de provedores</h3>
    <div className="grid gap-4 md:grid-cols-2">
      <label className="block text-sm font-medium text-gray-700">Provedor de transcrição
        <select aria-label="Provedor de transcrição" className="input mt-2" value={preferences.transcription_provider}
          onChange={(event) => updatePreference('transcription_provider', event.target.value)}>
          <option value="automatic">Automático</option>
          <option value="whisper" disabled={!providers.whisper.allowed}>{label('whisper')}</option>
          <option value="assemblyai" disabled={!providers.assemblyai.allowed}>{label('assemblyai')}</option>
        </select>
      </label>
      <label className="block text-sm font-medium text-gray-700">Provedor de inteligência de reuniões
        <select aria-label="Provedor de inteligência de reuniões" className="input mt-2" value={preferences.intelligence_provider}
          onChange={(event) => updatePreference('intelligence_provider', event.target.value)}>
          <option value="automatic">Automático</option>
          <option value="gemini" disabled={!providers.gemini.allowed}>{label('gemini')}</option>
        </select>
      </label>
    </div>
    <label className="mt-4 flex items-center gap-2 text-sm text-gray-700">
      <input type="checkbox" checked={preferences.use_diarization} onChange={(event) => updatePreference('use_diarization', event.target.checked)} />
      Ativar detecção de falantes por padrão
    </label>
    <div className="mt-4"><Button type="submit" icon={Save} loading={providerSaving} disabled={providerSaving}>Salvar preferências</Button></div>
  </form>
}

function ProviderCard({ title, provider, configuredProvider, credential, settings, saving, value, onChange, onSave, onRemove }) {
  const source = configuredProvider.credential_source
  const usesWhisper = provider === 'assemblyai'
    && settings.providers.whisper.allowed
    && ['automatic', 'whisper'].includes(settings.preferences.transcription_provider)
  const providerName = provider === 'assemblyai' ? 'AssemblyAI' : 'Gemini'
  const current = source === 'user' ? `${providerName} · Sua própria conta`
    : source === 'platform' ? `${providerName} · Fornecido pela USAGI`
      : provider === 'assemblyai' && usesWhisper ? 'Faster-Whisper' : 'Não conectado'
  const allowed = configuredProvider.allowed
  const statusLabel = allowed ? 'Disponível nesta conta'
    : provider === 'assemblyai' && usesWhisper ? 'Faster-Whisper disponível' : 'Indisponível'
  return <Card className="space-y-4">
    <CardHeader><div className="flex flex-wrap items-center gap-3"><CardTitle>{title}</CardTitle>
      <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${allowed || usesWhisper ? 'bg-primary-50 text-primary-800' : 'bg-amber-100 text-amber-950'}`}>{statusLabel}</span>
    </div></CardHeader>
    <CardContent className="space-y-4">
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center justify-between gap-2 text-sm text-gray-500"><span>Estado atual</span><span>{allowed ? 'Disponível' : 'Indisponível'}</span></div>
        <p className="mt-1 font-semibold text-gray-900">{current}</p>
        <p className="mt-1 text-sm text-gray-600">{provider === 'assemblyai'
          ? usesWhisper ? 'Faster-Whisper está disponível para a preferência atual desta conta. Você pode conectar sua conta AssemblyAI abaixo.'
            : allowed ? 'AssemblyAI está permitido para esta conta. Conecte sua própria credencial abaixo, se necessário.'
              : 'Nenhum provedor de transcrição está disponível para a preferência atual desta conta.'
          : 'O Gemini gera resumos, tópicos, decisões, tarefas e perguntas quando uma credencial permitida está conectada.'}</p>
      </div>
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
        <p className="text-sm font-medium text-gray-700">{credential.configured ? 'Credencial própria salva' : 'Conectar sua conta'}</p>
        {configuredProvider.credential_source === 'platform' && <p className="mt-1 text-sm text-gray-600">A credencial em uso é fornecida pela USAGI.</p>}
        {!settings.credential_storage_available && <p className="mt-2 text-sm text-amber-800">O armazenamento seguro de credenciais não está disponível no momento.</p>}
        {settings.credential_storage_available && <div className="mt-3 space-y-2">
          <label className="sr-only" htmlFor={`credential-${provider}`}>Credencial {provider === 'assemblyai' ? 'AssemblyAI' : 'Gemini'}</label>
          <input id={`credential-${provider}`} aria-label={`Credencial ${provider === 'assemblyai' ? 'AssemblyAI' : 'Gemini'}`} type="password" autoComplete="off"
            className="input" value={value} onChange={(event) => onChange(event.target.value)} placeholder={credential.configured ? 'Inserir nova credencial para substituir' : 'Inserir credencial'} />
          <div className="flex flex-wrap gap-2">
            <Button disabled={!value || saving} loading={saving} onClick={onSave}>{credential.configured ? 'Substituir credencial' : 'Salvar credencial'}</Button>
            {credential.configured && <Button variant="outline" disabled={saving} onClick={onRemove}>Remover credencial {provider === 'assemblyai' ? 'AssemblyAI' : 'Gemini'}</Button>}
          </div>
        </div>}
        <p className="mt-2 text-xs text-gray-500">Configurada indica que foi salva, mas não valida a chave ou a conta no serviço externo.</p>
      </div>
    </CardContent>
  </Card>
}

function LoadingState({ loading, error, retry }) {
  if (loading) return <p role="status">Carregando preferências dos provedores…</p>
  if (error) return <div role="alert" className="space-y-2"><p>Não foi possível carregar as preferências dos provedores.</p><Button variant="outline" onClick={retry}>Tentar novamente</Button></div>
  return null
}

function StatusRow({ label, value }) {
  return <div className="flex items-center justify-between border-b border-gray-100 py-2 last:border-0">
    <span className="text-gray-600">{label}</span>
    <span className="font-medium text-gray-900">{value}</span>
  </div>
}
