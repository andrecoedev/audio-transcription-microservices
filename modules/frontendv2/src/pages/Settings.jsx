import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Save, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'

import Button from '../components/Button'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import PageHeader from '../components/PageHeader'
import ProviderConnectionCard from '../components/ProviderConnectionCard'
import ProviderPreferences from '../components/ProviderPreferences'
import GoogleAccountLink from '../components/GoogleAccountLink'
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
  const [preferences, setPreferences] = useState(null)
  const [health, setHealth] = useState(null)
  const [statusError, setStatusError] = useState(false)
  const [statusLoading, setStatusLoading] = useState(false)
  const [providerError, setProviderError] = useState(false)
  const [providerLoading, setProviderLoading] = useState(true)
  const [providerSaving, setProviderSaving] = useState(false)
  const [credentialOperation, setCredentialOperation] = useState(null)
  const [credentials, setCredentials] = useState({ assemblyai: '', gemini: '' })
  const [profile, setProfile] = useState({ name: user?.name || '', email: user?.email || '' })
  const [errorMessage, setErrorMessage] = useState('')

  const refreshProviderSettings = useCallback(async () => {
    setProviderLoading(true)
    setErrorMessage('')
    try {
      const result = await audioService.getProviderSettings()
      setProviderSettings(result)
      setPreferences(result.preferences)
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

  const updatePreference = (key, value) => setPreferences((current) => ({ ...current, [key]: value }))

  const savePreferences = async (event) => {
    event.preventDefault()
    setProviderSaving(true)
    setErrorMessage('')
    try {
      const result = await audioService.updateProviderPreferences(preferences)
      setProviderSettings(result)
      setPreferences(result.preferences)
      toast.success('Preferências salvas')
    } catch {
      setErrorMessage('Não foi possível salvar as preferências. Tente novamente.')
      toast.error('Não foi possível salvar as preferências de provedores')
    } finally {
      setProviderSaving(false)
    }
  }

  const saveCredential = async (provider) => {
    const secret = credentials[provider]
    if (!secret) return false
    if (secret.length < 8 || secret.length > 4096 || /[^\x21-\x7e]/.test(secret)) {
      setCredentials((current) => ({ ...current, [provider]: '' }))
      setErrorMessage('Formato da chave inválido. Copie a chave de API do serviço, sem espaços, e tente novamente.')
      return false
    }
    setProviderSaving(true)
    setCredentialOperation(provider)
    setCredentials((current) => ({ ...current, [provider]: '' }))
    setErrorMessage('')
    try {
      setProviderSettings(await audioService.saveProviderCredential(provider, secret))
      toast.success('Chave salva com segurança')
      return true
    } catch (error) {
      setErrorMessage(error.status === 422
        ? 'Formato da chave inválido. Copie a chave de API do serviço, sem espaços, e tente novamente.'
        : error.status === 429 ? 'Muitas alterações em pouco tempo. Aguarde antes de tentar novamente.'
          : 'Não foi possível salvar a credencial. Tente novamente; se continuar, procure o suporte da USAGI.')
      toast.error('Não foi possível salvar a credencial')
      return false
    } finally {
      setCredentials((current) => ({ ...current, [provider]: '' }))
      setProviderSaving(false)
      setCredentialOperation(null)
    }
  }

  const removeCredential = async (provider) => {
    setProviderSaving(true)
    setCredentialOperation(provider)
    setErrorMessage('')
    try {
      setProviderSettings(await audioService.deleteProviderCredential(provider))
      toast.success('Credencial removida')
      return true
    } catch {
      setErrorMessage('Não foi possível remover a credencial. Tente novamente.')
      toast.error('Não foi possível remover a credencial')
      return false
    } finally {
      setCredentials((current) => ({ ...current, [provider]: '' }))
      setProviderSaving(false)
      setCredentialOperation(null)
    }
  }

  const saveProfileLocally = () => {
    updateProfile(profile)
    toast.success('Preferências locais atualizadas')
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader title="Configurações" description="Escolha como processar seu áudio e conecte suas contas de IA.">
        <Button variant="outline" size="sm" onClick={() => { refreshStatus(); refreshProviderSettings() }} loading={statusLoading || providerLoading} disabled={statusLoading || providerLoading || providerSaving} icon={RefreshCw}>Atualizar</Button>
      </PageHeader>

      <div role="tablist" aria-label="Seções das configurações" className="flex flex-wrap gap-2">
        {tabs.map((tab) => <button key={tab.id} id={`settings-tab-${tab.id}`} type="button" role="tab"
          aria-selected={activeTab === tab.id} aria-controls={`settings-panel-${tab.id}`} disabled={providerSaving}
          onClick={() => {
            setCredentials({ assemblyai: '', gemini: '' })
            setActiveTab(tab.id)
          }}
          className={`rounded-full border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${activeTab === tab.id ? 'border-primary-100 bg-primary-50 font-semibold text-primary-800' : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'}`}>
          {tab.label}
        </button>)}
      </div>
      {errorMessage && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{errorMessage}</p>}

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
            <GoogleAccountLink />
          </CardContent>
        </Card>}

        {activeTab === 'transcription' && <Card>
          <CardHeader><CardTitle>Preferências de transcrição</CardTitle></CardHeader>
          <CardContent>{providerSettings ? <ProviderPreferences settings={providerSettings} preferences={preferences} updatePreference={updatePreference}
            savePreferences={savePreferences} saving={providerSaving} /> : <LoadingState loading={providerLoading} error={providerError} retry={refreshProviderSettings} />}</CardContent>
        </Card>}

        {activeTab === 'ai' && <div className="space-y-6">
          {providerLoading && <p role="status" className="text-gray-600">Carregando serviços da sua conta…</p>}
          {providerError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">Não foi possível carregar os serviços de IA.
            <Button variant="outline" className="ml-3" onClick={refreshProviderSettings}>Tentar novamente</Button>
          </div>}
          {providerSettings && <>
            <div>
              <h2 className="text-2xl font-semibold text-gray-900">Serviços de IA</h2>
              <p className="mt-1 text-gray-600">Escolha o processamento nas preferências abaixo. Conectar sua própria conta define quem fornece e paga pelo serviço externo.</p>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <ProviderCard title="Transcrição de áudio" provider="assemblyai" configuredProvider={providerSettings.providers.assemblyai}
                credential={providerSettings.credentials.assemblyai} settings={providerSettings} saving={providerSaving} operation={credentialOperation}
                value={credentials.assemblyai} onChange={(value) => setCredentials({ ...credentials, assemblyai: value })}
                onSave={() => saveCredential('assemblyai')} onRemove={() => removeCredential('assemblyai')} />
              <ProviderCard title="Resumos inteligentes" provider="gemini" configuredProvider={providerSettings.providers.gemini}
                credential={providerSettings.credentials.gemini} settings={providerSettings} saving={providerSaving} operation={credentialOperation}
                value={credentials.gemini} onChange={(value) => setCredentials({ ...credentials, gemini: value })}
                onSave={() => saveCredential('gemini')} onRemove={() => removeCredential('gemini')} />
            </div>
            <ProviderPreferences settings={providerSettings} preferences={preferences} updatePreference={updatePreference}
              savePreferences={savePreferences} saving={providerSaving} />
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
                  <StatusRow label="Fila de processamento" value={health?.processing?.redis || 'não verificado'} />
                  <StatusRow label="Processamento de áudio" value={health?.processing
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


function ProviderCard({ provider, configuredProvider, credential, settings, saving, operation, value, onChange, onSave, onRemove }) {
  return <ProviderConnectionCard provider={provider} details={configuredProvider} credential={credential}
    storageAvailable={settings.credential_storage_available} busy={saving} saving={saving && operation === provider}
    value={value} onChange={onChange} onSave={onSave} onRemove={onRemove} />
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
