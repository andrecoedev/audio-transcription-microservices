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
import { formatCount, formatNumber } from '../utils/format'

const EMPTY_EXTENSIONS = []

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
    if (guestPolicy) return
    let active = true
    setPolicyError(false)
    guestService.policy().then((policy) => {
      if (active) {
        setPublicLimits(policy)
        setPolicyError(!Array.isArray(policy.allowed_extensions) || policy.allowed_extensions.length === 0)
      }
    }).catch(() => { if (active) setPolicyError(true) })
    return () => { active = false }
  }, [guestPolicy, policyAttempt])
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
  const authenticatedUploadPolicy = user ? providerSettings?.upload_policy : null
  const limits = guestPolicy || (authenticatedUploadPolicy || (publicAccount ? publicLimits : null))
  const developmentAccess = authenticatedUploadPolicy?.development_access === true
  const allowedExtensions = (guestPolicy || (user ? (authenticatedUploadPolicy || publicLimits) : publicLimits))?.allowed_extensions || EMPTY_EXTENSIONS
  const formatsLabel = allowedExtensions.map(extension => extension.toUpperCase()).join(', ')
  const policyReady = allowedExtensions.length > 0
  const processingAllowed = !guestPolicy || guestPolicy.can_create_job === true
  const maxFileSize = limits ? limits.max_upload_mb * 1024 * 1024 : MAX_FILE_SIZE
  const assemblyai = providerSettings?.providers?.assemblyai
  const canUsePlatformAssemblyAI = !guestPolicy && assemblyai?.available === true && assemblyai?.platform_access === true
  const canUseOwnAssemblyAI = !guestPolicy && assemblyai?.available === true && assemblyai?.byok_allowed === true
    && providerSettings?.credentials?.assemblyai?.configured === true
    && providerSettings?.credential_storage_available === true
  const canUseWhisper = !user || (providerSettings?.providers.whisper.available === true && providerSettings?.providers.whisper.allowed === true)
  const providerReady = !user || Boolean(providerSettings)
  const [file, setFile] = useState(null)
  const [options, setOptions] = useState({
    useDiarization: false,
    transcriptionModel: 'automatic',
    credentialSource: null,
  })
  useEffect(() => {
    if (!providerSettings) return
    setOptions({
      useDiarization: providerSettings.preferences.use_diarization,
      transcriptionModel: providerSettings.preferences.transcription_provider,
      credentialSource: null,
    })
  }, [providerSettings])
  const selectedProviderAvailable = options.transcriptionModel === 'automatic'
    || (options.transcriptionModel === 'assemblyai'
      ? options.credentialSource === 'platform' ? canUsePlatformAssemblyAI : options.credentialSource === 'user' && canUseOwnAssemblyAI
      : providerSettings?.providers[options.transcriptionModel]?.available === true && providerSettings?.providers[options.transcriptionModel]?.allowed === true)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)

  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      const selectedFile = acceptedFiles[0]
      const extension = selectedFile.name.split('.').pop().toLowerCase()
      if (!allowedExtensions.includes(extension)) {
        toast.error(`Este formato não está disponível. Envie um arquivo em ${formatsLabel}.`)
        return
      }
      
      if (selectedFile.size > maxFileSize) {
        toast.error(`O arquivo é maior que o limite de ${formatNumber(maxFileSize / (1024 * 1024), { maximumFractionDigits: 0 })} MB.`)
        return
      }
      
      setFile(selectedFile)
      toast.success('Arquivo selecionado.')
    }
  }, [maxFileSize, allowedExtensions, formatsLabel])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected: () => toast.error(`Selecione um único arquivo em um dos formatos disponíveis: ${formatsLabel}.`),
    accept: {
      'audio/*': allowedExtensions.map(extension => `.${extension}`),
      'video/*': allowedExtensions.map(extension => `.${extension}`),
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
        useDiarization: options.credentialSource === 'platform' ? true : options.useDiarization,
        onUploadProgress: (progressEvent) => {
          const percentCompleted = progressEvent.total
            ? Math.min(100, Math.round((progressEvent.loaded * 100) / progressEvent.total)) : 0
          setProgress(percentCompleted)
        }
      })

      toast.success('Áudio enviado e na fila para transcrição.')
      if (onCreated) onCreated(result)
      else navigate(`/transcriptions/${result.id}`)
    } catch (error) {
      toast.error(error.message || 'Não foi possível enviar o áudio. Tente novamente.')
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
        {developmentAccess && <p className="rounded-lg bg-primary-50 p-3 text-sm text-primary-900">Acesso de desenvolvimento para transcrição local. Os limites abaixo são tetos técnicos; serviços externos mantêm suas permissões e limites.</p>}
        {guestPolicy && !processingAllowed && <p role="status" className="text-sm text-gray-600 mt-2">{guestPolicy.unavailable_reason}</p>}

      {limits && <div className="flex flex-wrap gap-2 text-sm text-gray-700" aria-label="Limites desta conta">
        <span className="rounded-full bg-primary-50 px-3 py-1.5">{developmentAccess ? 'Teto técnico' : 'Máximo de'} {formatNumber(limits.max_upload_mb)} MB por arquivo</span>
        {limits.max_audio_seconds && <span className="rounded-full bg-primary-50 px-3 py-1.5">Até {formatCount(Math.floor(limits.max_audio_seconds / 60), 'minuto', 'minutos')} de áudio{developmentAccess ? ' (teto técnico)' : ''}</span>}
        {guestPolicy && <span className="rounded-full bg-primary-50 px-3 py-1.5">{formatCount(guestPolicy.jobs_per_session, 'transcrição temporária', 'transcrições temporárias')} por sessão</span>}
      </div>}

      {/* Upload Area */}
      <Card>
        <CardContent>
          {!policyReady ? (
            <div role="status">
              {policyError || guestPolicy ? <><p>Não foi possível consultar os limites e formatos de upload.</p>{!guestPolicy && <Button onClick={() => setPolicyAttempt((value) => value + 1)}>Tentar novamente</Button>}</> : <p>Consultando limites de upload...</p>}
            </div>
          ) : !file ? (
            <div
              {...getRootProps()}
              aria-disabled={!policyReady || !processingAllowed}
              className={`flex flex-col items-start justify-between gap-6 rounded-xl px-2 py-5 sm:flex-row sm:items-center transition-colors ${!processingAllowed ? 'cursor-not-allowed' : 'cursor-pointer'} ${
                isDragActive
                  ? 'border-primary-600 bg-primary-50'
                  : 'border-gray-300 bg-gray-50 hover:border-primary-500 hover:bg-primary-50/40'
              }`}
            >
              <input {...getInputProps()} disabled={!policyReady || !processingAllowed || uploading} />
              <div className="min-w-0 flex-1">
              <p className="text-xl font-semibold text-gray-900 mb-2">
                {isDragActive ? 'Solte o arquivo aqui' : 'Arraste um arquivo ou clique para selecionar'}
              </p>
              <p className="text-sm text-gray-500">
                Formatos disponíveis: {formatsLabel || 'consultando…'} ({developmentAccess ? 'teto técnico' : 'máximo de'} {formatNumber(maxFileSize / (1024 * 1024), { maximumFractionDigits: 0 })} MB)
              </p>
              </div>
              <span className={`inline-flex shrink-0 items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium ${processingAllowed ? 'bg-primary-600 text-white' : 'bg-gray-200 text-gray-500'}`}><Upload className="h-4 w-4" aria-hidden="true" />Escolher arquivo</span>
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
                      {formatNumber(file.size / (1024 * 1024), { maximumFractionDigits: 2 })} MB
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
        <Card className="!p-4"><p className="text-xs font-medium text-gray-500">Formatos disponíveis</p><p className="mt-1 text-sm text-gray-800">{formatsLabel || 'Consultando os formatos disponíveis…'}</p></Card>
        <Card className="!p-4"><p className="text-xs font-medium text-gray-500">{developmentAccess ? 'Tetos técnicos de envio' : 'Limites de envio'}</p><p className="mt-1 text-sm text-gray-800">{developmentAccess ? 'Até' : 'Máximo de'} {formatNumber(maxFileSize / (1024 * 1024), { maximumFractionDigits: 0 })} MB{limits?.max_audio_seconds ? ` e ${formatCount(Math.floor(limits.max_audio_seconds / 60), 'minuto', 'minutos')} por áudio${developmentAccess ? ' (teto técnico)' : ''}` : ''}.</p></Card>
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
            <span>Transcrição temporária</span>
            {!processingAllowed && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">Indisponível</span>}
          </div> : user && !providerSettings ? <div role={providerError ? 'alert' : 'status'} className="space-y-2">
            <p>{providerLoading ? 'Carregando opções de transcrição...' : 'Não foi possível carregar as opções de transcrição. O envio permanece bloqueado.'}</p>
            {providerError && <Button variant="outline" onClick={() => setProviderAttempt((value) => value + 1)}>Tentar novamente</Button>}
          </div> : <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Opção de transcrição
            </label>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {user && <button
                onClick={() => setOptions({ ...options, transcriptionModel: 'automatic', credentialSource: null })}
                aria-label="Automático"
                disabled={uploading}
                className={`p-4 border-2 rounded-lg transition-all ${options.transcriptionModel === 'automatic' ? 'border-primary-600 bg-primary-50' : 'border-gray-200 hover:border-gray-300'}`}
              >
                <p className="font-medium text-gray-900">Automático</p>
                <p className="text-xs text-gray-500">Segue sua configuração automática. Não seleciona a franquia do Beta.</p>
              </button>}

              {(!user || providerSettings) && <button
                onClick={() => setOptions({ ...options, transcriptionModel: 'whisper', credentialSource: null })}
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
                    <p className="font-medium text-gray-900">Transcrição local</p>
                  </div>
                </div>
              </button>}

              {user && providerSettings && <>
                <button
                  aria-label="Transcrição do Beta"
                  onClick={() => setOptions({ ...options, transcriptionModel: 'assemblyai', credentialSource: 'platform' })}
                  disabled={uploading || !canUsePlatformAssemblyAI}
                  className={`p-4 border-2 rounded-lg transition-all ${!canUsePlatformAssemblyAI ? 'border-gray-200 bg-gray-50 cursor-not-allowed' : options.transcriptionModel === 'assemblyai' && options.credentialSource === 'platform' ? 'border-primary-600 bg-primary-50' : 'border-gray-200 hover:border-gray-300'}`}
                >
                  <p className="font-medium text-gray-900">Transcrição do Beta</p>
                  {!canUsePlatformAssemblyAI && <span className="mt-1 inline-block rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">Indisponível</span>}
                  <p className="mt-1 text-xs text-gray-500">Detecção de falantes incluída na franquia desta rodada</p>
                </button>
                <button
                  aria-label="Minha chave de transcrição"
                  onClick={() => setOptions({ ...options, transcriptionModel: 'assemblyai', credentialSource: 'user' })}
                  disabled={uploading || !canUseOwnAssemblyAI}
                  className={`p-4 border-2 rounded-lg transition-all ${!canUseOwnAssemblyAI ? 'border-gray-200 bg-gray-50 cursor-not-allowed' : options.transcriptionModel === 'assemblyai' && options.credentialSource === 'user' ? 'border-primary-600 bg-primary-50' : 'border-gray-200 hover:border-gray-300'}`}
                >
                  <p className="font-medium text-gray-900">Minha chave de transcrição</p>
                  {!canUseOwnAssemblyAI && <span className="mt-1 inline-block rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">Indisponível</span>}
                  <p className="mt-1 text-xs text-gray-500">Usa sua chave AssemblyAI salva em Configurações</p>
                </button>
              </>}
            </div>
            {user && options.transcriptionModel !== 'automatic' && !selectedProviderAvailable && <p role="alert" className="text-sm text-amber-800">
              {options.transcriptionModel === 'assemblyai' && options.credentialSource === null
                ? 'Escolha explicitamente a Transcrição do Beta ou Minha chave de transcrição para usar a preferência salva.'
                : `A opção salva não está disponível. Conecte uma chave em Configurações ou escolha outra opção disponível.`}
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
                checked={options.credentialSource === 'platform' || options.useDiarization}
                onChange={(e) => setOptions({ ...options, useDiarization: e.target.checked })}
                disabled={uploading || options.credentialSource === 'platform'}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
            </label>
          </div>
          {!guestPolicy && user && providerSettings && !canUsePlatformAssemblyAI && !canUseOwnAssemblyAI && <Link to="/settings" className="inline-block text-sm text-primary-700 hover:underline">Ver serviços de IA em Configurações</Link>}
        </CardContent>
      </Card>

      {/* Ações */}
      <p className="text-sm text-gray-600">
        Ao usar transcrição externa, o áudio necessário ao processamento é enviado ao serviço selecionado, inclusive com sua própria chave.
        {' '}O áudio é removido da USAGI após o processamento; falhas de limpeza podem deixar a remoção pendente.
      </p>
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
          loadingLabel="Enviando..."
        >
          Iniciar Transcrição
        </Button>
      </div>
    </div>
  )
}
