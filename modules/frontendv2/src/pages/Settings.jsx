import { useCallback, useEffect, useState } from 'react'
import { Cpu, RefreshCw, Save } from 'lucide-react'
import toast from 'react-hot-toast'

import Button from '../components/Button'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import { audioService } from '../services/audioService'
import { useAuthStore } from '../stores/authStore'

export default function Settings() {
  const { user, updateProfile } = useAuthStore()
  const isAdmin = user?.roles?.includes('admin') ?? false
  const [health, setHealth] = useState(null)
  const [credentialStatus, setCredentialStatus] = useState(null)
  const [gpuDiag, setGpuDiag] = useState(null)
  const [loadingGpu, setLoadingGpu] = useState(false)
  const [profile, setProfile] = useState({
    name: user?.name || '',
    email: user?.email || '',
  })

  const refreshStatus = useCallback(async () => {
    try {
      const healthData = await audioService.checkHealth()
      setHealth(healthData)
      if (isAdmin) {
        setCredentialStatus(await audioService.getApiKeysStatus())
      }
    } catch (error) {
      toast.error(error.message || 'Erro ao verificar o sistema')
    }
  }, [isAdmin])

  useEffect(() => {
    refreshStatus()
  }, [refreshStatus])

  const checkGpuDiagnostics = async () => {
    try {
      setLoadingGpu(true)
      setGpuDiag(await audioService.getSystemGpu())
    } catch (error) {
      toast.error(error.message || 'Erro ao verificar o worker')
    } finally {
      setLoadingGpu(false)
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
          <StatusRow label="Banco" value={health?.database || 'indisponível'} />
          <StatusRow label="Whisper local" value={health?.models?.whisper?.configured ? 'configurado' : 'não configurado'} />
          <StatusRow label="Pyannote local" value={health?.models?.diarization?.configured ? 'configurado' : 'não configurado'} />
          <StatusRow label="AssemblyAI externo" value={credentialStatus?.aai_api_key?.configured ? 'configurado' : 'não configurado'} />
          <StatusRow label="Gemini externo" value={credentialStatus?.gemini_api_key?.configured ? 'configurado' : 'não configurado'} />
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
          <div className="flex items-center justify-between">
            <CardTitle>Diagnóstico de processamento</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={checkGpuDiagnostics}
              loading={loadingGpu}
              icon={Cpu}
            >
              Verificar worker
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-600">
            {gpuDiag?.deprecated
              ? 'CUDA e modelos pertencem ao RQ worker; consulte os logs do worker.'
              : 'O diagnóstico detalhado fica disponível no processo de worker.'}
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
