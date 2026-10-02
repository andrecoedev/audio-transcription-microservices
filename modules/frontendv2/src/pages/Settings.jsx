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

  useEffect(() => {
    refreshStatus()
  }, [refreshStatus])

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
          Provider configurado no servidor não significa acesso às credenciais USAGI. Conectar credenciais próprias (BYOK) ainda não está disponível.
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
        <CardHeader><CardTitle>Credenciais de provedores</CardTitle></CardHeader>
        <CardContent>
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
            Credenciais são segredos da infraestrutura. Configure <code>HF_TOKEN</code>,{' '}
            <code>AAI_API_KEY</code> e <code>GEMINI_API_KEY</code> no ambiente ou no mecanismo
            de secrets do deployment e reinicie o worker. A interface não recebe nem armazena chaves.
          </div>
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
