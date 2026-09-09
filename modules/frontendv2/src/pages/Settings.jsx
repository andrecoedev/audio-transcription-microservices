import { useState, useEffect } from 'react'
import { Settings as SettingsIcon, Save, RefreshCw, Key, Eye, EyeOff, Cpu, Zap, AlertTriangle, CheckCircle, XCircle, Activity } from 'lucide-react'
import Card, { CardHeader, CardTitle, CardContent } from '../components/Card'
import Button from '../components/Button'
import ApiKeyGuide from '../components/ApiKeyGuide'
import { audioService } from '../services/audioService'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'

export default function Settings() {
  const { user, updateProfile } = useAuthStore()
  const [health, setHealth] = useState(null)
  const [profile, setProfile] = useState({
    name: user?.name || '',
    email: user?.email || '',
  })
  const [apiKeys, setApiKeys] = useState({
    hfToken: '',
    aaiApiKey: '',
    geminiApiKey: '',
  })
  const [showKeys, setShowKeys] = useState({
    hfToken: false,
    aaiApiKey: false,
    geminiApiKey: false,
  })
  const [loading, setLoading] = useState(false)
  const [savingKeys, setSavingKeys] = useState(false)
  const [gpuDiag, setGpuDiag] = useState(null)
  const [loadingGpu, setLoadingGpu] = useState(false)

  useEffect(() => {
    checkSystemHealth()
    loadApiKeysStatus()
  }, [])

  const loadApiKeysStatus = async () => {
    try {
      await audioService.getApiKeysStatus()
      // Status carregado
    } catch (error) {
      console.error('Erro ao carregar status das API Keys:', error)
    }
  }

  const checkSystemHealth = async () => {
    try {
      const data = await audioService.checkHealth()
      setHealth(data)
    } catch (error) {
      toast.error('Erro ao verificar saúde do sistema')
      console.error(error)
    }
  }

  const checkGpuDiagnostics = async () => {
    try {
      setLoadingGpu(true)
      const data = await audioService.getSystemGpu()
      setGpuDiag(data)
      if (data.deprecated) {
        toast('O diagnóstico de GPU agora pertence aos logs do worker.', { icon: 'ℹ️' })
      } else if (data.gpu_being_used) {
        toast.success('✅ GPU detectada e em uso!')
      } else if (data.gpu?.cuda_available) {
        toast('⚠️ GPU detectada mas não está sendo usada pelos engines.', { icon: '⚠️' })
      } else {
        toast.error('❌ GPU (CUDA) não disponível. Usando CPU.')
      }
    } catch (error) {
      toast.error('Erro ao verificar GPU: ' + (error.message || 'backend indisponível'))
      console.error(error)
    } finally {
      setLoadingGpu(false)
    }
  }

  const handleSaveProfile = () => {
    updateProfile(profile)
    toast.success('Perfil atualizado com sucesso!')
  }

  const handleSaveApiKeys = async () => {
    try {
      setSavingKeys(true)
      
      // Validar se pelo menos uma chave foi preenchida
      if (!apiKeys.hfToken && !apiKeys.aaiApiKey && !apiKeys.geminiApiKey) {
        toast.error('Preencha pelo menos uma chave de API')
        return
      }
      
      // Enviar para o backend
      const result = await audioService.updateApiKeys(apiKeys)

      // ── 1. Chaves salvas com sucesso no banco ──────────────────────────────
      if (result.keys_saved) {
        toast.success('✅ Chaves salvas com sucesso!', { duration: 4000 })
      }

      // ── 2. Modelos que carregaram com sucesso ──────────────────────────────
      if (result.updated_models && result.updated_models.length > 0) {
        const modelsMsg = result.updated_models
          .map(m => `✅ ${m.model}: ${m.device}`)
          .join('\n')
        toast.success(modelsMsg, {
          duration: 6000,
          style: { whiteSpace: 'pre-line' },
        })
      }

      // ── 3. Erros de engine (aviso, não erro crítico — chave já foi salva) ──
      if (result.errors && result.errors.length > 0) {
        result.errors.forEach(error => {
          if (error.includes('Token inválido') || error.includes('401')) {
            toast(
              <div className="space-y-2">
                <p className="font-semibold">⚠️ {error}</p>
                <p className="text-xs">
                  Verifique se:
                  <br />• O token está correto (começa com hf_)
                  <br />• Tem permissão "Read"
                  <br />• Foi criado em: huggingface.co/settings/tokens
                </p>
                <p className="text-xs text-green-700 font-medium">
                  💾 A chave foi salva e será usada no próximo restart.
                </p>
              </div>,
              { duration: 10000, icon: '⚠️' }
            )
          } else if (error.includes('Acesso negado') || error.includes('403')) {
            toast(
              <div className="space-y-2">
                <p className="font-semibold">⚠️ {error}</p>
                <p className="text-xs">
                  Aceite os termos de uso:
                  <br />• https://huggingface.co/pyannote/speaker-diarization
                  <br />• https://huggingface.co/pyannote/segmentation
                </p>
                <p className="text-xs text-green-700 font-medium">
                  💾 A chave foi salva e será usada no próximo restart.
                </p>
              </div>,
              { duration: 10000, icon: '⚠️' }
            )
          } else {
            toast(error, { duration: 8000, icon: '⚠️' })
          }
        })
      }

      // ── 4. Sucesso total — nenhum erro ─────────────────────────────────────
      if (result.worker_restart_required) {
        toast('ℹ️ Reinicie o RQ worker para aplicar as chaves.', { duration: 6000 })
      }

      // Atualizar status do sistema
      await checkSystemHealth()

    } catch (error) {
      console.error(error)
      toast.error('Erro de comunicação com o backend: ' + (error.response?.data?.detail || error.message))
    } finally {
      setSavingKeys(false)
    }
  }

  const toggleKeyVisibility = (key) => {
    setShowKeys(prev => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Configurações</h1>
        <p className="text-gray-600 mt-1">Gerencie as configurações do sistema</p>
      </div>

      {/* Perfil do Usuário */}
      <Card>
        <CardHeader>
          <CardTitle>👤 Perfil do Usuário</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Nome
            </label>
            <input
              type="text"
              value={profile.name}
              onChange={(e) => setProfile({ ...profile, name: e.target.value })}
              className="input"
              placeholder="Seu nome"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Email
            </label>
            <input
              type="email"
              value={profile.email}
              onChange={(e) => setProfile({ ...profile, email: e.target.value })}
              className="input"
              placeholder="seu@email.com"
            />
          </div>

          <Button onClick={handleSaveProfile} icon={Save}>
            Salvar Alterações
          </Button>
        </CardContent>
      </Card>

      {/* Status do Sistema */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>🔧 Status do Sistema</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={checkSystemHealth}
              icon={RefreshCw}
            >
              Atualizar
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {health ? (
            <>
              <ModelStatus
                name="Pyannote (Diarização)"
                configured={health.models?.diarization?.configured}
                device={health.models?.diarization?.device}
              />
              <ModelStatus
                name="Whisper (Transcrição Local)"
                configured={health.models?.whisper?.configured}
                device={health.models?.whisper?.device}
              />
              <ModelStatus
                name="AssemblyAI (Transcrição Cloud)"
                configured={health.models?.assemblyai?.configured}
                device={health.models?.assemblyai?.device}
              />
              <ModelStatus
                name="Gemini (Geração de Atas)"
                configured={health.models?.gemini?.configured}
                device={health.models?.gemini?.device}
              />
            </>
          ) : (
            <p className="text-gray-500">Carregando status...</p>
          )}
        </CardContent>
      </Card>

      {/* Configuração de API Keys */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>🔑 Chaves de API</CardTitle>
            <ApiKeyGuide />
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
            <p className="text-sm text-blue-800">
              <strong>💡 Como funciona:</strong> A API salva as chaves com segurança. Reinicie o RQ worker para carregar os engines com a nova configuração.
            </p>
          </div>

          {/* Alertas de Requisitos */}
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 space-y-2">
            <h4 className="text-sm font-semibold text-yellow-900">⚠️ Requisitos do Hugging Face Token:</h4>
            <ul className="text-xs text-yellow-800 space-y-1 list-disc list-inside ml-2">
              <li>Token deve ter permissão <strong>"Read"</strong></li>
              <li>Token deve começar com <code className="bg-yellow-100 px-1 rounded">hf_</code></li>
              <li>Para Pyannote, aceite os termos em:
                <ul className="ml-4 mt-1 space-y-1">
                  <li>→ <a href="https://huggingface.co/pyannote/speaker-diarization" target="_blank" rel="noopener noreferrer" className="text-yellow-900 underline hover:text-yellow-700">speaker-diarization</a></li>
                  <li>→ <a href="https://huggingface.co/pyannote/segmentation" target="_blank" rel="noopener noreferrer" className="text-yellow-900 underline hover:text-yellow-700">segmentation</a></li>
                </ul>
              </li>
            </ul>
          </div>

          {/* Hugging Face Token */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              🤗 Hugging Face Token
              <span className="text-xs text-gray-500 ml-2">(Para Pyannote)</span>
            </label>
            <div className="relative">
              <input
                type={showKeys.hfToken ? 'text' : 'password'}
                value={apiKeys.hfToken}
                onChange={(e) => setApiKeys({ ...apiKeys, hfToken: e.target.value })}
                className="input pr-10"
                placeholder="hf_xxxxxxxxxxxxxxxxxxxxx"
              />
              <button
                type="button"
                onClick={() => toggleKeyVisibility('hfToken')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showKeys.hfToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Obtenha em: <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:underline">https://huggingface.co/settings/tokens</a>
            </p>
          </div>

          {/* AssemblyAI API Key */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              ☁️ AssemblyAI API Key
              <span className="text-xs text-gray-500 ml-2">(Para transcrição cloud)</span>
            </label>
            <div className="relative">
              <input
                type={showKeys.aaiApiKey ? 'text' : 'password'}
                value={apiKeys.aaiApiKey}
                onChange={(e) => setApiKeys({ ...apiKeys, aaiApiKey: e.target.value })}
                className="input pr-10"
                placeholder="xxxxxxxxxxxxxxxxxxxxxxxx"
              />
              <button
                type="button"
                onClick={() => toggleKeyVisibility('aaiApiKey')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showKeys.aaiApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Obtenha em: <a href="https://www.assemblyai.com/dashboard/signup" target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:underline">https://www.assemblyai.com/dashboard</a>
            </p>
          </div>

          {/* Gemini API Key */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              ✨ Google Gemini API Key
              <span className="text-xs text-gray-500 ml-2">(Para geração de atas de reunião)</span>
            </label>
            <div className="relative">
              <input
                type={showKeys.geminiApiKey ? 'text' : 'password'}
                value={apiKeys.geminiApiKey}
                onChange={(e) => setApiKeys({ ...apiKeys, geminiApiKey: e.target.value })}
                className="input pr-10"
                placeholder="AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
              />
              <button
                type="button"
                onClick={() => toggleKeyVisibility('geminiApiKey')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showKeys.geminiApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Obtenha em: <a href="https://makersuite.google.com/app/apikey" target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:underline">https://makersuite.google.com/app/apikey</a>
            </p>
          </div>

          {/* Instruções */}
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-green-900 mb-2">✨ Ativação no Worker:</h4>
            <ul className="text-sm text-green-800 space-y-1 list-disc list-inside">
              <li>Digite suas chaves nos campos acima</li>
              <li>Clique em "Salvar chaves"</li>
              <li>Reinicie somente o processo RQ worker</li>
              <li>A API permanece leve durante o carregamento</li>
            </ul>
          </div>

          <Button
            onClick={handleSaveApiKeys}
            loading={savingKeys}
            disabled={!apiKeys.hfToken && !apiKeys.aaiApiKey && !apiKeys.geminiApiKey}
            icon={Save}
            className="w-full"
          >
            {savingKeys ? 'Salvando...' : 'Salvar chaves'}
          </Button>
        </CardContent>
      </Card>

      {/* Diagnóstico de GPU e Hardware */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>🖥️ Diagnóstico de Hardware</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={checkGpuDiagnostics}
              loading={loadingGpu}
              icon={Cpu}
            >
              {loadingGpu ? 'Verificando...' : 'Verificar GPU'}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {gpuDiag?.deprecated ? (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
              O diagnóstico de CUDA/PyTorch foi removido da API. Consulte os logs do RQ worker para verificar GPU e engines.
            </div>
          ) : !gpuDiag ? (
            <div className="text-center py-8 text-gray-400">
              <Cpu className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Clique em <strong>Verificar GPU</strong> para ver o diagnóstico de hardware</p>
            </div>
          ) : (
            <>
              {/* Status geral */}
              <div className={`flex items-center gap-3 p-4 rounded-xl border-2 ${
                gpuDiag.gpu_being_used
                  ? 'bg-green-50 border-green-200'
                  : gpuDiag.gpu?.cuda_available
                  ? 'bg-yellow-50 border-yellow-200'
                  : 'bg-red-50 border-red-200'
              }`}>
                {gpuDiag.gpu_being_used ? (
                  <CheckCircle className="w-8 h-8 text-green-500 shrink-0" />
                ) : gpuDiag.gpu?.cuda_available ? (
                  <AlertTriangle className="w-8 h-8 text-yellow-500 shrink-0" />
                ) : (
                  <XCircle className="w-8 h-8 text-red-500 shrink-0" />
                )}
                <div>
                  <p className="font-semibold text-gray-900">
                    {gpuDiag.gpu_being_used
                      ? '✅ GPU em uso — ótimo desempenho!'
                      : gpuDiag.gpu?.cuda_available
                      ? '⚠️ GPU detectada mas modelos estão em CPU'
                      : '❌ GPU não disponível — usando CPU (lento + alto consumo de RAM)'}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    PyTorch {gpuDiag.gpu?.pytorch_version}
                    {gpuDiag.gpu?.cuda_version ? ` • CUDA ${gpuDiag.gpu.cuda_version}` : ''}
                  </p>
                </div>
              </div>

              {/* GPU(s) detectadas */}
              {gpuDiag.gpu?.devices?.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">🎮 GPU Detectada</h4>
                  {gpuDiag.gpu.devices.map(dev => (
                    <div key={dev.id} className="bg-gray-50 rounded-lg p-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-gray-900">{dev.name}</span>
                        <span className="text-xs text-gray-500">Compute {dev.compute_capability}</span>
                      </div>
                      {/* Barra de VRAM */}
                      <div>
                        <div className="flex justify-between text-xs text-gray-600 mb-1">
                          <span>VRAM: {dev.allocated_vram_gb.toFixed(1)}GB em uso</span>
                          <span>Total: {dev.total_vram_gb.toFixed(1)}GB</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div
                            className={`h-2 rounded-full transition-all ${
                              (dev.allocated_vram_gb / dev.total_vram_gb) > 0.85
                                ? 'bg-red-500'
                                : (dev.allocated_vram_gb / dev.total_vram_gb) > 0.6
                                ? 'bg-yellow-500'
                                : 'bg-green-500'
                            }`}
                            style={{ width: `${Math.min(100, (dev.allocated_vram_gb / dev.total_vram_gb) * 100)}%` }}
                          />
                        </div>
                        <p className="text-xs text-gray-500 mt-1">
                          Livre: {dev.free_vram_gb.toFixed(1)}GB • Reservado: {dev.reserved_vram_gb.toFixed(1)}GB
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* RAM do sistema */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2">💾 RAM do Sistema</h4>
                <div className="bg-gray-50 rounded-lg p-3 space-y-2">
                  <div className="flex justify-between text-xs text-gray-600 mb-1">
                    <span>Em uso: {gpuDiag.ram?.used_gb?.toFixed(1)}GB</span>
                    <span>Total: {gpuDiag.ram?.total_gb?.toFixed(1)}GB ({gpuDiag.ram?.percent}%)</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all ${
                        gpuDiag.ram?.percent >= 90
                          ? 'bg-red-500'
                          : gpuDiag.ram?.percent >= 75
                          ? 'bg-yellow-500'
                          : 'bg-green-500'
                      }`}
                      style={{ width: `${gpuDiag.ram?.percent || 0}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-500">
                    Disponível: {gpuDiag.ram?.available_gb?.toFixed(1)}GB
                    {gpuDiag.ram?.status === 'critical' && ' ⚠️ RAM crítica!'}
                  </p>
                </div>
              </div>

              {/* Device de cada engine */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2">⚡ Device dos Engines</h4>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(gpuDiag.engines || {}).map(([name, device]) => {
                    const isGpu = device.toLowerCase().includes('cuda')
                    const isCloud = device === 'cloud'
                    const isLoaded = device !== 'not loaded'
                    return (
                      <div key={name} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                        <span className="text-xs font-medium text-gray-700 capitalize">{name}</span>
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          isGpu ? 'bg-green-100 text-green-700'
                          : isCloud ? 'bg-blue-100 text-blue-700'
                          : isLoaded ? 'bg-yellow-100 text-yellow-700'
                          : 'bg-gray-100 text-gray-500'
                        }`}>
                          {isGpu ? '🎮 ' : isCloud ? '☁️ ' : isLoaded ? '💻 ' : ''}{device}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Problemas encontrados */}
              {gpuDiag.issues?.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-red-700">🔴 Problemas Detectados</h4>
                  {gpuDiag.issues.map((issue, i) => (
                    <div key={i} className="flex gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                      <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                      <p className="text-xs text-red-800">{issue}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Recomendações */}
              {gpuDiag.recommendations?.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-blue-700">💡 Recomendações</h4>
                  {gpuDiag.recommendations.map((rec, i) => (
                    <div key={i} className="flex gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                      <Zap className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
                      <p className="text-xs text-blue-800">{rec}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Informações do Sistema */}
      <Card>
        <CardHeader>
          <CardTitle>ℹ️ Informações do Sistema</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <InfoRow label="Versão" value="2.0.0" />
          <InfoRow label="API Backend" value="http://localhost:2020" />
          <InfoRow label="Status da API" value={health ? '🟢 Online' : '🔴 Offline'} />
          <InfoRow label="Banco de Dados" value={health?.database || 'N/A'} />
        </CardContent>
      </Card>

      {/* Links Úteis */}
      <Card>
        <CardHeader>
          <CardTitle>🔗 Links Úteis</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <LinkRow
            label="Hugging Face - Criar Token"
            url="https://huggingface.co/settings/tokens"
          />
          <LinkRow
            label="AssemblyAI - Criar Conta"
            url="https://www.assemblyai.com/dashboard/signup"
          />
          <LinkRow
            label="Google Gemini - Obter API Key"
            url="https://makersuite.google.com/app/apikey"
          />
          <LinkRow
            label="Pyannote - Aceitar Termos de Uso"
            url="https://huggingface.co/pyannote/speaker-diarization"
          />
          <LinkRow
            label="Documentação do Projeto"
            url="https://github.com/Dec0XD/audio-transcription-microservices"
          />
        </CardContent>
      </Card>
    </div>
  )
}

function ModelStatus({ name, configured, device }) {
  return (
    <div className="flex items-center justify-between p-3 border border-gray-200 rounded-lg">
      <div>
        <p className="font-medium text-gray-900">{name}</p>
        <p className="text-sm text-gray-500">{device || 'Não configurado'}</p>
      </div>
      <span
        className={`badge ${configured ? 'badge-success' : 'badge-error'}`}
      >
        {configured ? 'Configurado' : 'Não configurado'}
      </span>
    </div>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
      <span className="text-gray-600">{label}</span>
      <span className="font-medium text-gray-900">{value}</span>
    </div>
  )
}

function LinkRow({ label, url }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
      <span className="text-gray-600">{label}</span>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary-600 hover:text-primary-700 text-sm font-medium hover:underline"
      >
        Acessar →
      </a>
    </div>
  )
}
