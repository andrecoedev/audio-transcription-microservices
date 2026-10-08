import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'

import Button from '../components/Button'
import PageHeader from '../components/PageHeader'
import HelpPopover from '../components/HelpPopover'
import ProviderConnectionCard from '../components/ProviderConnectionCard'
import { ProviderPreferenceFields, PreferenceSaveButton } from '../components/ProviderPreferences'
import AccountSettings from '../components/AccountSettings'
import UsageOverview from '../components/UsageOverview'
import { audioService } from '../services/audioService'
import { useAuthStore } from '../stores/authStore'

export default function Settings() {
  const userId = useAuthStore(state => state.user?.id)
  return <SettingsPage key={userId ?? 'guest'} />
}

function SettingsPage() {
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
  const [usageOpen, setUsageOpen] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  const refreshProviderSettings = useCallback(async () => {
    setCredentials({ assemblyai: '', gemini: '' })
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
      toast.error('Não foi possível salvar as preferências de serviços')
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

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader title="Configurações">
        <a href="#plan-usage" className="text-sm font-medium text-primary-800 hover:underline" onClick={() => setUsageOpen(true)}>Plano e consumo</a>
        <Button variant="outline" size="sm" onClick={() => { refreshStatus(); refreshProviderSettings() }} loading={statusLoading || providerLoading} disabled={statusLoading || providerLoading || providerSaving} icon={RefreshCw}>Atualizar</Button>
      </PageHeader>

      {errorMessage && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{errorMessage}</p>}

      <div className="space-y-8">
        <SettingsSection id="account" title="Minha conta" help="Nome e e-mail vêm da sua conta. A edição destes dados ainda não está disponível; esta tela não altera sua identidade nem a propriedade dos arquivos.">
          <AccountSettings />
        </SettingsSection>

        <form onSubmit={savePreferences} className="space-y-8">
          <SettingsSection id="transcription" title="Transcrição">
            {providerSettings ? <ProviderPreferenceFields kind="transcription" settings={providerSettings} preferences={preferences}
              updatePreference={updatePreference} saving={providerSaving} /> : <LoadingState loading={providerLoading} error={providerError} retry={refreshProviderSettings} />}
          </SettingsSection>
          <SettingsSection id="intelligence" title="Resumos inteligentes">
            {providerSettings ? <ProviderPreferenceFields kind="intelligence" settings={providerSettings} preferences={preferences}
              updatePreference={updatePreference} saving={providerSaving} /> : <p className="text-sm text-gray-600">{providerLoading ? 'Carregando preferências…' : 'As preferências de resumo estão indisponíveis.'}</p>}
          </SettingsSection>
          {providerSettings && <PreferenceSaveButton settings={providerSettings} preferences={preferences} saving={providerSaving} />}
        </form>

        <SettingsSection id="connections" title="Serviços conectados">
          <div className="space-y-5">
          {providerLoading && <p role="status" className="text-gray-600">Carregando serviços da sua conta…</p>}
          {providerError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">Não foi possível carregar os serviços de IA.
            <Button variant="outline" className="ml-3" onClick={refreshProviderSettings}>Tentar novamente</Button>
          </div>}
          {providerSettings && <>
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
            <details className="rounded-lg border border-gray-200 bg-white p-4">
              <summary className="cursor-pointer font-medium text-gray-900">Diagnóstico do sistema</summary>
              <div className="mt-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <p className="text-sm text-gray-600">Estado reportado pelos serviços da USAGI.</p>
                </div>
                {statusError && <p role="alert" className="mb-2 text-sm text-red-700">Não foi possível consultar o sistema. Tente novamente.</p>}
                <div className="space-y-2 text-sm">
                  <StatusRow label="Proteção de credenciais BYOK" value={providerSettings.credential_storage_available ? 'configurada' : 'indisponível: verificar PROVIDER_CREDENTIAL_ENCRYPTION_KEY na API e no Worker'} />
                  <StatusRow label="Banco de dados" value={healthStatus(health?.database)} />
                  <StatusRow label="Fila de processamento" value={healthStatus(health?.processing?.redis)} />
                  <StatusRow label="Processamento de áudio" value={health?.processing
                    ? health.processing.worker_available ? 'disponível' : 'indisponível' : 'não verificado'} />
                  {[
                    ['Transcrição local', 'whisper'], ['Detecção de falantes', 'diarization'],
                    ['Transcrição via AssemblyAI', 'assemblyai'], ['Resumos via Gemini', 'gemini'],
                  ].map(([label, provider]) => <StatusRow key={provider} label={label} value={
                    health?.models?.[provider] ? health.models[provider].configured ? 'configurado' : 'não configurado' : 'não verificado'
                  } />)}
                </div>
                <p className="mt-3 text-xs text-gray-500">Configuração reportada não comprova carregamento dos modelos nem disponibilidade de APIs externas.</p>
                <p className="mt-3 text-sm"><Link to="/meeting-minutes" className="font-medium text-primary-800 hover:underline">Abrir atas de reunião</Link></p>
              </div>
            </details>
          </>}
          </div>
        </SettingsSection>
      </div>
      <details id="plan-usage" open={usageOpen} onToggle={event => setUsageOpen(event.currentTarget.open)} className="border-t border-gray-200 pt-4">
        <summary className="cursor-pointer font-medium text-gray-900">Plano e consumo</summary>
        {usageOpen && <div className="mt-4"><UsageOverview /></div>}
      </details>
    </div>
  )
}


function SettingsSection({ id, title, help, children }) {
  return <section aria-labelledby={`settings-${id}`} className="border-b border-gray-200 pb-6 last:border-0">
    <div className="mb-3 flex items-center gap-2"><h2 id={`settings-${id}`} className="text-lg font-semibold text-gray-900">{title}</h2>
      {help && <HelpPopover label={title}>{help}</HelpPopover>}</div>
    {children}
  </section>
}

function ProviderCard({ provider, configuredProvider, credential, settings, saving, operation, value, onChange, onSave, onRemove }) {
  return <ProviderConnectionCard provider={provider} details={configuredProvider} credential={credential}
    storageAvailable={settings.credential_storage_available} busy={saving} saving={saving && operation === provider}
    value={value} onChange={onChange} onSave={onSave} onRemove={onRemove} />
}

function LoadingState({ loading, error, retry }) {
  if (loading) return <p role="status">Carregando preferências dos serviços…</p>
  if (error) return <div role="alert" className="space-y-2"><p>Não foi possível carregar as preferências dos serviços.</p><Button variant="outline" onClick={retry}>Tentar novamente</Button></div>
  return null
}

function StatusRow({ label, value }) {
  return <div className="grid gap-1 sm:grid-cols-2 sm:gap-3 border-b border-gray-100 py-2 last:border-0">
    <span className="text-gray-600">{label}</span>
    <span className="min-w-0 break-words font-medium text-gray-900">{value}</span>
  </div>
}

function healthStatus(value) {
  if (value === 'connected') return 'Disponível'
  if (value === 'unavailable') return 'Indisponível'
  return 'Não verificado'
}
