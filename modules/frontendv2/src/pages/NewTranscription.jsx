import { useState, useCallback, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { Upload, FileAudio, Zap, Users } from 'lucide-react'
import ProcessingStatus from '../components/ProcessingStatus'
import Button from '../components/Button'
import { audioService } from '../services/audioService'
import { MAX_FILE_SIZE } from '../utils/constants'
import toast from 'react-hot-toast'
import { useAuthStore } from '../stores/authStore'
import { guestService } from '../services/guestService'
import { formatCount, formatNumber } from '../utils/format'
import './NewTranscription.css'

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

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    onDropRejected: () => toast.error(`Selecione um único arquivo em um dos formatos disponíveis: ${formatsLabel}.`),
    accept: {
      'audio/*': allowedExtensions.map(extension => `.${extension}`),
      'video/*': allowedExtensions.map(extension => `.${extension}`),
    },
    maxFiles: 1,
    multiple: false,
    noClick: true,
    disabled: !policyReady || !processingAllowed || uploading,
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

  const chooseProcessing = (selection) => setOptions({
    ...options,
    transcriptionModel: selection.transcriptionModel,
    credentialSource: selection.credentialSource,
  })

  const maxFileSizeLabel = formatNumber(maxFileSize / (1024 * 1024), { maximumFractionDigits: 0 })
  const limitsLabel = limits ? `${developmentAccess ? 'Teto técnico' : 'Máximo de'} ${formatNumber(limits.max_upload_mb)} MB por arquivo${limits.max_audio_seconds ? ` · Até ${formatCount(Math.floor(limits.max_audio_seconds / 60), 'minuto', 'minutos')} de áudio${developmentAccess ? ' (teto técnico)' : ''}` : ''}${guestPolicy ? ` · ${formatCount(guestPolicy.jobs_per_session, 'transcrição temporária', 'transcrições temporárias')} por sessão` : ''}` : `Máximo de ${maxFileSizeLabel} MB por arquivo`

  return (
    <div className="editorial-upload">
      <header className="editorial-upload__header">
        <div>
          <p className="editorial-upload__eyebrow">Nova transcrição</p>
          <h1 className="editorial-title">Envie o áudio da reunião.</h1>
          <p className="editorial-upload__intro">A transcrição fica pronta para revisar, exportar e virar resumo.</p>
        </div>
        {user && <Link className="editorial-upload__history" to="/transcriptions">Histórico</Link>}
      </header>

      {developmentAccess && <p className="editorial-upload__notice">
        Acesso de desenvolvimento para transcrição local. Os limites abaixo são tetos técnicos; serviços externos mantêm suas permissões e limites.
      </p>}
      {guestPolicy && !processingAllowed && <p role="status" className="editorial-upload__status">{guestPolicy.unavailable_reason}</p>}

      <section className={`editorial-upload__dropzone${file ? ' is-selected' : ''}${isDragActive ? ' is-dragging' : ''}${!processingAllowed ? ' is-disabled' : ''}`}
        {...getRootProps({
          role: 'group',
          'aria-label': 'Envio de áudio',
          'aria-disabled': !policyReady || !processingAllowed,
        })}>
        <input {...getInputProps()} disabled={!policyReady || !processingAllowed || uploading} />
        {!policyReady ? (
          <div className="editorial-upload__policy-state" role={policyError || guestPolicy ? 'alert' : 'status'}>
            {policyError || guestPolicy ? <>
              <p>Não foi possível consultar os limites e formatos de upload.</p>
              {!guestPolicy && <Button variant="outline" onClick={() => setPolicyAttempt(value => value + 1)}>Tentar novamente</Button>}
            </> : <p>Consultando limites de upload...</p>}
          </div>
        ) : <>
          <svg className="editorial-upload__wave" viewBox="0 0 120 40" aria-hidden="true">
            <path d="M2 20h8M14 12v16M22 6v28M30 14v12M38 9v22M46 16v8M54 4v32M62 12v16M70 18v4M78 8v24M86 14v12M94 10v20M102 17v6M110 20h8" />
          </svg>

          {file ? <div className="editorial-upload__file">
            <p className="editorial-upload__eyebrow">Arquivo selecionado</p>
            <div className="editorial-upload__file-row">
              <FileAudio aria-hidden="true" className="editorial-upload__file-icon" />
              <div className="editorial-upload__file-info">
                <p className="editorial-upload__file-name">{file.name}</p>
                <p className="editorial-upload__file-meta">{formatNumber(file.size / (1024 * 1024), { maximumFractionDigits: 2 })} MB · ainda não enviado</p>
              </div>
            </div>
            <div className="editorial-upload__file-actions">
              <button type="button" className="editorial-upload__text-button" onClick={(event) => { event.stopPropagation(); open() }} disabled={uploading}>Trocar arquivo</button>
              <button type="button" className="editorial-upload__text-button" onClick={(event) => { event.stopPropagation(); removeFile() }} aria-label="Remover arquivo selecionado" disabled={uploading}>Remover</button>
            </div>
            {uploading && <ProcessingStatus status="uploading" uploadProgress={progress} />}
          </div> : <div className="editorial-upload__empty">
            <p className="editorial-upload__drop-title">{isDragActive ? 'Solte o arquivo aqui' : 'Arraste um arquivo ou clique para selecionar'}</p>
            <div className="editorial-upload__meta" aria-label="Limites desta conta">
              <p>Formatos disponíveis: {formatsLabel || 'consultando…'}</p>
              <p>{limitsLabel}</p>
            </div>
            <button type="button" className="editorial-upload__choose" onClick={(event) => { event.stopPropagation(); open() }} disabled={!processingAllowed || uploading}>
              <Upload aria-hidden="true" size={17} />Escolher arquivo
            </button>
          </div>}
        </>}
      </section>

      <section className="editorial-upload__preferences" aria-labelledby="processing-option-title">
        <fieldset className="editorial-upload__choices">
          <legend id="processing-option-title">Opção de transcrição</legend>

          {guestPolicy ? <div className="editorial-upload__guest-option">
            <span>Transcrição temporária</span>
            {!processingAllowed && <span className="editorial-upload__badge">Indisponível</span>}
          </div> : user && !providerSettings ? <div role={providerError ? 'alert' : 'status'} className="editorial-upload__provider-state">
            <p>{providerLoading ? 'Carregando opções de transcrição...' : 'Não foi possível carregar as opções de transcrição. O envio permanece bloqueado.'}</p>
            {providerError && <Button variant="outline" onClick={() => setProviderAttempt(value => value + 1)}>Tentar novamente</Button>}
          </div> : <div className="editorial-upload__choice-list">
            {user && <button type="button" aria-label="Automático" aria-pressed={options.transcriptionModel === 'automatic'} disabled={uploading}
              onClick={() => chooseProcessing({ transcriptionModel: 'automatic', credentialSource: null })} className="editorial-upload__choice">
              <span className="editorial-upload__choice-copy"><strong>Automático</strong><small>Segue sua configuração automática. Não seleciona a franquia do Beta.</small></span>
            </button>}

            {(!user || providerSettings) && <button type="button" aria-label="Transcrição local" aria-pressed={options.transcriptionModel === 'whisper'} disabled={uploading || (user && !canUseWhisper)}
              onClick={() => chooseProcessing({ transcriptionModel: 'whisper', credentialSource: null })} className="editorial-upload__choice">
              <Zap aria-hidden="true" className="editorial-upload__choice-icon" />
              <span className="editorial-upload__choice-copy"><strong>Transcrição local</strong></span>
            </button>}

            {user && providerSettings && <>
              <button type="button" aria-label="Transcrição do Beta" aria-pressed={options.transcriptionModel === 'assemblyai' && options.credentialSource === 'platform'} disabled={uploading || !canUsePlatformAssemblyAI}
                onClick={() => chooseProcessing({ transcriptionModel: 'assemblyai', credentialSource: 'platform' })} className="editorial-upload__choice">
                <span className="editorial-upload__choice-copy"><strong>Transcrição do Beta{!canUsePlatformAssemblyAI && <span className="editorial-upload__badge">Indisponível</span>}</strong><small>Detecção de falantes incluída na franquia desta rodada</small></span>
              </button>
              <button type="button" aria-label="Minha chave de transcrição" aria-pressed={options.transcriptionModel === 'assemblyai' && options.credentialSource === 'user'} disabled={uploading || !canUseOwnAssemblyAI}
                onClick={() => chooseProcessing({ transcriptionModel: 'assemblyai', credentialSource: 'user' })} className="editorial-upload__choice">
                <span className="editorial-upload__choice-copy"><strong>Minha chave de transcrição{!canUseOwnAssemblyAI && <span className="editorial-upload__badge">Indisponível</span>}</strong><small>Usa sua chave AssemblyAI salva em Configurações.</small></span>
              </button>
            </>}
          </div>}

          {user && providerSettings && options.transcriptionModel !== 'automatic' && !selectedProviderAvailable && <p role="alert" className="editorial-upload__warning">
            {options.transcriptionModel === 'assemblyai' && options.credentialSource === null
              ? 'Escolha explicitamente a Transcrição do Beta ou Minha chave de transcrição para usar a preferência salva.'
              : 'A opção salva não está disponível. Conecte uma chave em Configurações ou escolha outra opção disponível.'}
          </p>}
        </fieldset>

        <label className={`editorial-upload__diarization${options.credentialSource === 'platform' ? ' is-forced' : ''}`}>
          <span className="editorial-upload__diarization-copy"><Users aria-hidden="true" /><span><strong>Detecção de falantes</strong><small>Identifica diferentes falantes no áudio.</small></span></span>
          <input type="checkbox" role="switch" aria-label="Detecção de falantes"
            checked={options.credentialSource === 'platform' || options.useDiarization}
            onChange={event => setOptions({ ...options, useDiarization: event.target.checked })}
            disabled={uploading || options.credentialSource === 'platform'} />
        </label>

        {!guestPolicy && user && providerSettings && !canUsePlatformAssemblyAI && !canUseOwnAssemblyAI && <Link to="/settings" className="editorial-upload__settings-link">Ver serviços de IA em Configurações</Link>}
      </section>

      <footer className="editorial-upload__footer">
        <p className="editorial-upload__privacy">
          Ao usar transcrição externa, o áudio necessário ao processamento é enviado ao serviço selecionado, inclusive com sua própria chave. O áudio é removido da USAGI após o processamento; falhas de limpeza podem deixar a remoção pendente.
        </p>
        <div className="editorial-upload__actions">
          <Button variant="outline" className="editorial-upload__cancel" onClick={() => navigate(guestPolicy ? '/' : '/transcriptions')} disabled={uploading}>Cancelar</Button>
          <Button className="editorial-upload__submit" onClick={handleSubmit}
            disabled={!file || uploading || !policyReady || !processingAllowed || !providerReady || !selectedProviderAvailable}
            loading={uploading} loadingLabel="Enviando...">Iniciar Transcrição</Button>
        </div>
      </footer>
    </div>
  )
}
