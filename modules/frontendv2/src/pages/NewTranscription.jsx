import { useState, useCallback, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { Upload, FileAudio, X, Zap, Users } from 'lucide-react'
import Card, { CardHeader, CardTitle, CardContent } from '../components/Card'
import ProcessingStatus from '../components/ProcessingStatus'
import Button from '../components/Button'
import PageHeader from '../components/PageHeader'
import { audioService } from '../services/audioService'
import { MAX_FILE_SIZE } from '../utils/constants'
import toast from 'react-hot-toast'
import { useAuthStore } from '../stores/authStore'
import { guestService } from '../services/guestService'

export default function NewTranscription({ guestPolicy = null, onCreate = null, onCreated = null }) {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)
  const publicAccount = !guestPolicy && user?.registration_source === 'public'
  const [publicLimits, setPublicLimits] = useState(null)
  const [providerSettings, setProviderSettings] = useState(null)
  const [providerError, setProviderError] = useState(false)
  const [providerLoading, setProviderLoading] = useState(false)
  const [providerAttempt, setProviderAttempt] = useState(0)
  const [policyError, setPolicyError] = useState(false)
  const [policyAttempt, setPolicyAttempt] = useState(0)
  useEffect(() => {
    if (!publicAccount) return
    let active = true
    setPolicyError(false)
    guestService.policy().then((policy) => {
      if (active) setPublicLimits(policy)
    }).catch(() => { if (active) setPolicyError(true) })
    return () => { active = false }
  }, [publicAccount, policyAttempt])
  useEffect(() => {
    if (guestPolicy || !user) return
    let active = true
    setProviderLoading(true)
    setProviderError(false)
    audioService.getProviderSettings().then((settings) => {
      if (active) setProviderSettings(settings)
    }).catch(() => {
      if (active) {
        setProviderSettings(null)
        setProviderError(true)
      }
    }).finally(() => { if (active) setProviderLoading(false) })
    return () => { active = false }
  }, [guestPolicy, user, providerAttempt])
  const limits = guestPolicy || (publicAccount ? publicLimits : null)
  const policyReady = !publicAccount || Boolean(publicLimits)
  const processingAllowed = !guestPolicy || guestPolicy.can_create_job === true
  const maxFileSize = limits ? limits.max_upload_mb * 1024 * 1024 : MAX_FILE_SIZE
  const canUseAssemblyAI = !guestPolicy && providerSettings?.providers.assemblyai.available === true && providerSettings?.providers.assemblyai.allowed === true
  const canUseWhisper = !user || (providerSettings?.providers.whisper.available === true && providerSettings?.providers.whisper.allowed === true)
  const providerReady = !user || Boolean(providerSettings)
  const [file, setFile] = useState(null)
  const [options, setOptions] = useState({
    useDiarization: false,
    transcriptionModel: 'automatic'
  })
  useEffect(() => {
    if (!providerSettings) return
    setOptions({
      useDiarization: providerSettings.preferences.use_diarization,
      transcriptionModel: providerSettings.preferences.transcription_provider,
    })
  }, [providerSettings])
  const selectedProviderAvailable = options.transcriptionModel === 'automatic'
    || (providerSettings?.providers[options.transcriptionModel]?.available === true && providerSettings?.providers[options.transcriptionModel]?.allowed === true)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)

  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      const selectedFile = acceptedFiles[0]
      
      if (selectedFile.size > maxFileSize) {
        toast.error(`Arquivo muito grande! Máximo: ${(maxFileSize / (1024 * 1024)).toFixed(0)}MB`)
        return
      }
      
      setFile(selectedFile)
      toast.success('Arquivo carregado com sucesso!')
    }
  }, [maxFileSize])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected: () => toast.error('Arquivo rejeitado. Selecione um único arquivo em um dos formatos suportados.'),
    accept: {
      'audio/*': ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.opus'],
      'video/*': ['.mp4']
    },
    maxFiles: 1,
    multiple: false,
    disabled: !policyReady || !processingAllowed
  })

  const handleSubmit = async () => {
    if (!file || !policyReady || !processingAllowed || !providerReady) {
      toast.error('Selecione um arquivo primeiro')
      return
    }

    try {
      setUploading(true)
      setProgress(0)

      const result = await (onCreate || audioService.createTranscriptionJob)(file, {
        ...options,
        transcriptionModel: guestPolicy ? 'assemblyai' : options.transcriptionModel,
        onUploadProgress: (progressEvent) => {
          const percentCompleted = progressEvent.total
            ? Math.min(100, Math.round((progressEvent.loaded * 100) / progressEvent.total)) : 0
          setProgress(percentCompleted)
        }
      })

      toast.success('Arquivo enviado. Job de transcrição enfileirado!')
      if (onCreated) onCreated(result)
      else navigate(`/transcriptions/${result.id}`)
    } catch (error) {
      toast.error(error.message || 'Erro ao processar arquivo')
    } finally {
      setUploading(false)
      setProgress(0)
    }
  }

  const removeFile = () => {
    setFile(null)
    setProgress(0)
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <PageHeader title="Nova Transcrição" description="Envie um arquivo de áudio e obtenha uma transcrição para revisar e compartilhar.">
        {user && <Link to="/transcriptions" className="rounded-lg border bg-white px-4 py-2 text-sm hover:bg-gray-50">Histórico</Link>}
      </PageHeader>
        {guestPolicy && !processingAllowed && <p role="status" className="text-sm text-gray-600 mt-2">{guestPolicy.unavailable_reason}</p>}

      {limits && <div className="flex flex-wrap gap-2 text-sm text-gray-700" aria-label="Limites desta conta">
        <span className="rounded-full bg-primary-50 px-3 py-1.5">Máximo {limits.max_upload_mb} MB por arquivo</span>
        {limits.max_audio_seconds && <span className="rounded-full bg-primary-50 px-3 py-1.5">Até {Math.floor(limits.max_audio_seconds / 60)} minutos de áudio</span>}
        {guestPolicy && <span className="rounded-full bg-primary-50 px-3 py-1.5">{guestPolicy.jobs_per_session} transcrição temporária por sessão</span>}
      </div>}

      {/* Upload Area */}
      <Card>
        <CardContent>
          {!policyReady ? (
            <div role="status">
              {policyError ? <><p>Não foi possível consultar os limites de upload.</p><Button onClick={() => setPolicyAttempt((value) => value + 1)}>Tentar novamente</Button></> : <p>Consultando limites de upload...</p>}
            </div>
          ) : !file ? (
            <div
              {...getRootProps()}
              className={`flex flex-wrap items-center justify-between gap-6 rounded-xl px-2 py-5 cursor-pointer transition-colors ${
                isDragActive
                  ? 'border-primary-600 bg-primary-50'
                  : 'border-gray-300 bg-gray-50 hover:border-primary-500 hover:bg-primary-50/40'
              }`}
            >
              <input {...getInputProps()} />
              <div className="min-w-0 flex-1">
              <p className="text-xl font-semibold text-gray-900 mb-2">
                {isDragActive ? 'Solte o arquivo aqui' : 'Arraste um arquivo ou clique para selecionar'}
              </p>
              <p className="text-sm text-gray-500">
                Formatos suportados: MP3, WAV, MP4, M4A, FLAC, OGG, OPUS (máx. {(maxFileSize / (1024 * 1024)).toFixed(0)}MB)
              </p>
              </div>
              <span className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-medium text-white"><Upload className="h-4 w-4" aria-hidden="true" />Escolher arquivo</span>
            </div>
          ) : (
            <div className="border border-gray-200 rounded-lg p-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="p-3 bg-primary-100 rounded-lg">
                    <FileAudio className="w-6 h-6 text-primary-600" />
                  </div>
                  <div className="min-w-0">
                    <p className="break-all font-medium text-gray-900">{file.name}</p>
                    <p className="text-sm text-gray-500">
                      {(file.size / (1024 * 1024)).toFixed(2)} MB
                    </p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={removeFile}
                  aria-label="Remover arquivo selecionado"
                  disabled={uploading}
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>

              {uploading && <ProcessingStatus status="uploading" uploadProgress={progress} />}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-3 md:grid-cols-3">
        <Card className="!p-4"><p className="text-xs font-medium text-gray-500">Formatos aceitos</p><p className="mt-1 text-sm text-gray-800">MP3, WAV, M4A, FLAC, OGG, OPUS e MP4.</p></Card>
        <Card className="!p-4"><p className="text-xs font-medium text-gray-500">Limites de envio</p><p className="mt-1 text-sm text-gray-800">Máximo de {(maxFileSize / (1024 * 1024)).toFixed(0)} MB{limits?.max_audio_seconds ? ` e ${Math.floor(limits.max_audio_seconds / 60)} min por áudio` : ''}.</p></Card>
        <Card className="!p-4"><p className="text-xs font-medium text-gray-500">Exportação</p><p className="mt-1 text-sm text-gray-800">Transcrição disponível em TXT, SRT, VTT e JSON após a conclusão.</p></Card>
      </div>

      {/* Opções */}
      <Card className="!p-4">
        <CardHeader>
          <CardTitle>Preferências da transcrição</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Modelo de Transcrição */}
          {guestPolicy ? <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
            <span>Transcrição com AssemblyAI</span>
            {!processingAllowed && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">Indisponível</span>}
          </div> : user && !providerSettings ? <div role={providerError ? 'alert' : 'status'} className="space-y-2">
            <p>{providerLoading ? 'Carregando preferências dos provedores...' : 'Não foi possível carregar as preferências dos provedores. O envio permanece bloqueado.'}</p>
            {providerError && <Button variant="outline" onClick={() => setProviderAttempt((value) => value + 1)}>Tentar novamente</Button>}
          </div> : <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Modelo de Transcrição
            </label>
            <div className="grid gap-3 sm:grid-cols-3">
              {user && <button
                onClick={() => setOptions({ ...options, transcriptionModel: 'automatic' })}
                aria-label="Automático"
                disabled={uploading}
                className={`p-4 border-2 rounded-lg transition-all ${options.transcriptionModel === 'automatic' ? 'border-primary-600 bg-primary-50' : 'border-gray-200 hover:border-gray-300'}`}
              >
                <p className="font-medium text-gray-900">Automático</p>
                <p className="text-xs text-gray-500">AssemblyAI próprio quando configurado; caso contrário, processamento local</p>
              </button>}

              {(!user || providerSettings) && <button
                onClick={() => setOptions({ ...options, transcriptionModel: 'whisper' })}
                disabled={uploading || (user && !canUseWhisper)}
                className={`p-4 border-2 rounded-lg transition-all ${
                  options.transcriptionModel === 'whisper'
                    ? 'border-primary-600 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Zap className={`w-5 h-5 ${
                    options.transcriptionModel === 'whisper' ? 'text-primary-600' : 'text-gray-400'
                  }`} />
                  <div className="text-left">
                    <p className="font-medium text-gray-900">Faster-Whisper</p>
                    <p className="text-xs text-gray-500">Processamento local</p>
                  </div>
                </div>
              </button>}

              {user && providerSettings && <button
                onClick={() => setOptions({ ...options, transcriptionModel: 'assemblyai' })}
                disabled={uploading || !canUseAssemblyAI}
                className={`p-4 border-2 rounded-lg transition-all ${!canUseAssemblyAI ? 'border-gray-200 bg-gray-50 cursor-not-allowed' :
                  options.transcriptionModel === 'assemblyai'
                    ? 'border-primary-600 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Zap className={`w-5 h-5 ${
                    options.transcriptionModel === 'assemblyai' ? 'text-primary-600' : 'text-gray-400'
                  }`} />
                  <div className="text-left">
                    <p className="font-medium text-gray-900">AssemblyAI</p>
                    {!canUseAssemblyAI && <span className="mt-1 inline-block rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">Indisponível</span>}
                    <p className="mt-1 text-xs text-gray-500">{canUseAssemblyAI ? 'Habilitado para esta conta' : 'Verifique sua credencial e a disponibilidade em Configurações'}</p>
                  </div>
                </div>
              </button>}
            </div>
            {user && options.transcriptionModel !== 'automatic' && !selectedProviderAvailable && <p role="alert" className="text-sm text-amber-800">
              A preferência salva para {options.transcriptionModel === 'assemblyai' ? 'AssemblyAI' : 'Faster-Whisper'} não está disponível. Conecte a credencial em Configurações ou escolha Automático ou um provedor disponível.
            </p>}
          </div>}

          {/* Diarização */}
          <div className="flex items-center justify-between gap-3 p-3 border border-gray-200 rounded-lg">
            <div className="flex items-center gap-3">
              <Users className="w-5 h-5 text-gray-600" />
              <div>
                <p className="font-medium text-gray-900">Detecção de falantes</p>
                <p className="text-sm text-gray-500">Identifica diferentes falantes no áudio</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                aria-label="Detecção de falantes"
                checked={options.useDiarization}
                onChange={(e) => setOptions({ ...options, useDiarization: e.target.checked })}
                disabled={uploading}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
            </label>
          </div>
          {!guestPolicy && user && providerSettings && !canUseAssemblyAI && <Link to="/settings" className="inline-block text-sm text-primary-700 hover:underline">Ver serviços de IA em Configurações</Link>}
        </CardContent>
      </Card>

      {/* Ações */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          onClick={() => navigate(guestPolicy ? '/' : '/transcriptions')}
          disabled={uploading}
        >
          Cancelar
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={!file || uploading || !policyReady || !processingAllowed || !providerReady || !selectedProviderAvailable}
          loading={uploading}
        >
          Iniciar Transcrição
        </Button>
      </div>
    </div>
  )
}
