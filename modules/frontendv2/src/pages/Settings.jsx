import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Save } from 'lucide-react'
import toast from 'react-hot-toast'

import Button from '../components/Button'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import { audioService } from '../services/audioService'
import { useAuthStore } from '../stores/authStore'

export default function Settings() {
  const { user, updateProfile } = useAuthStore()
  const [health, setHealth] = useState(null)
  const [statusError, setStatusError] = useState(false)
  const [providerSettings, setProviderSettings] = useState(null)
  const [providerError, setProviderError] = useState(false)
  const [providerLoading, setProviderLoading] = useState(true)
  const [providerSaving, setProviderSaving] = useState(false)
  const [credentials, setCredentials] = useState({ assemblyai: '', gemini: '' })
  const [profile, setProfile] = useState({
    name: user?.name || '',
    email: user?.email || '',
  })

  const refreshStatus = useCallback(async () => {
    try {
      setStatusError(false)
      const healthData = await audioService.checkHealth()
      setHealth(healthData)
    } catch (error) {
      setHealth(null)
      setStatusError(true)
      toast.error(error.message || 'Erro ao verificar o sistema')
    }
  }, [])

  const refreshProviderSettings = useCallback(async () => {
    setProviderLoading(true)
    try {
      const data = await audioService.getProviderSettings()
      setProviderSettings(data)
      setProviderError(false)
    } catch {
      setProviderSettings(null)
      setProviderError(true)
    } finally {
      setProviderLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshStatus()
    refreshProviderSettings()
  }, [refreshStatus, refreshProviderSettings])

  const savePreferences = async (event) => {
    event.preventDefault()
    setProviderSaving(true)
    try {
      const data = await audioService.updateProviderPreferences(providerSettings.preferences)
      setProviderSettings(data)
      toast.success('Preferências de provedores salvas')
    } catch {
      toast.error('Não foi possível salvar as preferências de provedores')
    } finally {
      setProviderSaving(false)
    }
  }

  const saveCredential = async (provider) => {
    const secret = credentials[provider]
    if (!secret) return
    setProviderSaving(true)
    try {
      const data = await audioService.saveProviderCredential(provider, secret)
      setProviderSettings(data)
      toast.success('Credencial salva com segurança')
    } catch {
      toast.error('Não foi possível salvar a credencial')
    } finally {
      setCredentials((current) => ({ ...current, [provider]: '' }))
      setProviderSaving(false)
    }
  }

  const removeCredential = async (provider) => {
    setProviderSaving(true)
    try {
      const data = await audioService.deleteProviderCredential(provider)
      setProviderSettings(data)
      toast.success('Credencial removida')
    } catch {
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
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Configurações</h1>
        <p className="text-gray-600 mt-1">Perfil local e estado dos serviços</p>
        {user?.registration_source === 'public' && <p className="text-sm text-gray-600 mt-2">
          Suas credenciais são protegidas e usadas conforme as preferências da sua conta.
        </p>}
      </div>

      <Card>
        <CardHeader><CardTitle>Perfil</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <label className="block text-sm font-medium text-gray-700">
            Nome
            <input
              type="text"
              value={profile.name}
              onChange={(event) => setProfile({ ...profile, name: event.target.value })}
              className="input mt-2"
            />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            Email
            <input
              type="email"
              value={profile.email}
              onChange={(event) => setProfile({ ...profile, email: event.target.value })}
              className="input mt-2"
            />
          </label>
          <Button onClick={saveProfileLocally} icon={Save}>Salvar preferências locais</Button>
          <p className="text-xs text-gray-500">
            A edição de perfil permanece local ao navegador nesta versão.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Status do sistema</CardTitle>
            <Button variant="outline" size="sm" onClick={refreshStatus} icon={RefreshCw}>
              Atualizar
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {statusError && <p role="alert">Não foi possível consultar o sistema. Use Atualizar para tentar novamente.</p>}
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
          <p className="text-xs text-gray-500">Configuração não comprova carregamento dos modelos ou disponibilidade das APIs externas.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Provedores e preferências</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          {providerError && <div role="alert" className="space-y-2">
            <p>Não foi possível carregar as preferências dos provedores.</p>
            <Button variant="outline" onClick={refreshProviderSettings}>Tentar novamente</Button>
          </div>}
          {providerLoading && <p role="status">Carregando preferências dos provedores...</p>}
          {providerSettings && <>
            <form onSubmit={savePreferences} className="space-y-4">
              <label className="block text-sm font-medium text-gray-700">
                Provedor de transcrição
                <select aria-label="Provedor de transcrição" className="input mt-2"
                  value={providerSettings.preferences.transcription_provider}
                  onChange={(event) => setProviderSettings({ ...providerSettings, preferences: {
                    ...providerSettings.preferences, transcription_provider: event.target.value,
                  } })}>
                  <option value="automatic">Automático</option>
                  <option value="whisper" disabled={!providerSettings.providers.whisper.allowed}>
                    {providerSettings.providers.whisper.allowed ? 'Faster-Whisper' : 'Faster-Whisper (indisponível nesta conta)'}
                  </option>
                  <option value="assemblyai" disabled={!providerSettings.providers.assemblyai.allowed}>
                    {providerSettings.providers.assemblyai.allowed ? 'AssemblyAI' : 'AssemblyAI (credencial necessária)'}
                  </option>
                </select>
              </label>
              <label className="block text-sm font-medium text-gray-700">
                Provedor de inteligência de reuniões
                <select aria-label="Provedor de inteligência de reuniões" className="input mt-2"
                  value={providerSettings.preferences.intelligence_provider}
                  onChange={(event) => setProviderSettings({ ...providerSettings, preferences: {
                    ...providerSettings.preferences, intelligence_provider: event.target.value,
                  } })}>
                  <option value="automatic">Automático</option>
                  <option value="gemini" disabled={!providerSettings.providers.gemini.allowed}>
                    {providerSettings.providers.gemini.allowed ? 'Gemini' : 'Gemini (credencial necessária)'}
                  </option>
                </select>
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" checked={providerSettings.preferences.use_diarization}
                  onChange={(event) => setProviderSettings({ ...providerSettings, preferences: {
                    ...providerSettings.preferences, use_diarization: event.target.checked,
                  } })} />
                Ativar detecção de falantes por padrão
              </label>
              <Button type="submit" icon={Save} loading={providerSaving} disabled={providerSaving}>
                Salvar preferências
              </Button>
            </form>

            <div className="space-y-4 border-t border-gray-100 pt-4">
              {['assemblyai', 'gemini'].map((provider) => {
                const title = provider === 'assemblyai' ? 'AssemblyAI' : 'Gemini'
                const credential = providerSettings.credentials[provider]
                return <section key={provider} className="space-y-2">
                  <h3 className="font-medium text-gray-900">{title}</h3>
                  <p className="text-sm text-gray-600">
                    {credential.configured ? 'Credencial própria configurada' : 'Nenhuma credencial própria configurada'}
                    {providerSettings.providers[provider].credential_source && ` · Origem em uso: ${providerSettings.providers[provider].credential_source === 'user' ? 'sua conta' : 'plataforma'}`}
                    {!providerSettings.providers[provider].allowed && ' · Credencial necessária para habilitar este provedor'}
                  </p>
                  {credential.configured && <Button variant="outline" size="sm" disabled={providerSaving}
                    onClick={() => removeCredential(provider)}>Remover credencial {title}</Button>}
                  {providerSettings.credential_storage_available && <div className="flex flex-col gap-2 sm:flex-row">
                    <input aria-label={`Credencial ${title}`} type="password" autoComplete="off"
                      className="input" value={credentials[provider]}
                      onChange={(event) => setCredentials({ ...credentials, [provider]: event.target.value })}
                      placeholder={credential.configured ? 'Substituir credencial' : 'Inserir credencial'} />
                    <Button disabled={!credentials[provider] || providerSaving}
                      loading={providerSaving} onClick={() => saveCredential(provider)}>
                      {credential.configured ? 'Substituir' : 'Salvar credencial'}
                    </Button>
                  </div>}
                </section>
              })}
              <p className="text-xs text-gray-500">As chaves nunca são exibidas novamente. O estado mostra apenas se há uma credencial configurada.</p>
            </div>
          </>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Diagnóstico de processamento</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-600">
            CUDA e modelos pertencem ao RQ worker; o diagnóstico detalhado é operacional, nos logs do worker.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

function StatusRow({ label, value }) {
  return (
    <div className="flex items-center justify-between border-b border-gray-100 py-2 last:border-0">
      <span className="text-gray-600">{label}</span>
      <span className="font-medium text-gray-900">{value}</span>
    </div>
  )
}
