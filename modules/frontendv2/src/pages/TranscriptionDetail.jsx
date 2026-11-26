import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { 
  ArrowLeft, 
  ChevronDown,
  Copy,
  CheckCircle2
} from 'lucide-react'
import Button from '../components/Button'
import ProcessingStatus from '../components/ProcessingStatus'
import PageHeader from '../components/PageHeader'
import { audioService } from '../services/audioService'
import { requestErrorMessage } from '../services/requestError'
import { formatDuration, formatNumber, formatSeconds, getDisplayFilename } from '../utils/format'
import toast from 'react-hot-toast'
import '../styles/editorial-workspace.css'

export default function TranscriptionDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [transcription, setTranscription] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [pollingError, setPollingError] = useState(false)
  const [copied, setCopied] = useState(false)
  const displayFilename = getDisplayFilename(transcription)
  const canExportTranscript = transcription?.status === 'completed' && Boolean(transcription?.segments?.length)

  const loadTranscription = useCallback(async ({ silent = false } = {}) => {
    try {
      if (!silent) setLoading(true)
      const data = await audioService.getTranscription(id)
      setTranscription(data)
      setLoadError(false)
      setPollingError(false)
    } catch {
      if (!silent) setLoadError(true)
      else setPollingError(true)
      if (!silent) {
        toast.error('Erro ao carregar transcrição')
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }, [id])

  useEffect(() => {
    loadTranscription()
  }, [loadTranscription])

  useEffect(() => {
    if (!['queued', 'processing'].includes(transcription?.status)) {
      return
    }

    const timer = setInterval(() => {
      loadTranscription({ silent: true })
    }, 3000)

    return () => clearInterval(timer)
  }, [transcription?.status, loadTranscription])

  const copyToClipboard = async () => {
    const text = transcription.segments
      .map(seg => `[${seg.speaker}] ${seg.text}`)
      .join('\n\n')
    
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      toast.success('Texto copiado para a área de transferência')
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      toast.error('Erro ao copiar texto')
    }
  }

  const downloadAsText = () => {
    const text = transcription.segments
      .map(seg => `[${seg.speaker}] (${seg.start.toFixed(1)}s - ${seg.end.toFixed(1)}s)\n${seg.text}`)
      .join('\n\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${displayFilename}_transcricao.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadAsJSON = () => {
    const blob = new Blob([JSON.stringify(transcription, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${displayFilename}_transcricao.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadAsVTT = () => {
    let vtt = 'WEBVTT\n\n'
    transcription.segments.forEach((seg) => {
      const start = formatVTTTime(seg.start)
      const end = formatVTTTime(seg.end)
      vtt += `${start} --> ${end}\n${seg.text}\n\n`
    })
    
    const blob = new Blob([vtt], { type: 'text/vtt' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${displayFilename}_legendas.vtt`
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadAsSRT = () => {
    let srt = ''
    transcription.segments.forEach((seg, i) => {
      srt += `${i + 1}\n${formatSubtitleTime(seg.start, ',')} --> ${formatSubtitleTime(seg.end, ',')}\n${seg.text}\n\n`
    })
    downloadTextFile(srt, `${displayFilename}_legendas.srt`, 'text/plain')
  }

  const formatSubtitleTime = (seconds, decimalSeparator) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const wholeSeconds = Math.floor(seconds % 60)
    const milliseconds = Math.floor((seconds % 1) * 1000)
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(wholeSeconds).padStart(2, '0')}${decimalSeparator}${String(milliseconds).padStart(3, '0')}`
  }

  const downloadTextFile = (text, filename, type) => {
    const blob = new Blob([text], { type })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const formatVTTTime = (seconds) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)
    const ms = Math.floor((seconds % 1) * 1000)
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Carregando transcrição...</p>
        </div>
      </div>
    )
  }

  if (!transcription) {
    return (
      <div role={loadError ? 'alert' : undefined} className="text-center py-12">
        <p className="text-gray-600">Transcrição não encontrada</p>
        {loadError && <Button variant="outline" className="mt-4" onClick={() => loadTranscription()}>Tentar novamente</Button>}
        <Link to="/transcriptions" className="btn-primary mt-4">Voltar para Transcrições</Link>
      </div>
    )
  }

  if (['queued', 'processing'].includes(transcription.status)) {
    return <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="Transcrevendo áudio" description={`${displayFilename} · ${formatDuration(transcription.duration_seconds)}`} />
      <ProcessingStatus status={transcription.status} />
      {pollingError && <p role="status" className="text-sm text-amber-800">Não foi possível atualizar o status. Exibindo a última informação recebida.</p>}
      <Link to="/transcriptions" className="inline-flex items-center text-sm font-medium text-gray-600 hover:text-gray-900">
        <ArrowLeft className="mr-2 h-4 w-4" />Voltar ao histórico
      </Link>
    </div>
  }

  return (
    <div className="mx-auto min-w-0 max-w-6xl space-y-6">
      {/* Header */}
      <header className="editorial-workspace-header">
        <div className="min-w-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/transcriptions')}
            icon={ArrowLeft}
          >
            Voltar
          </Button>
          <div className="mt-2 min-w-0">
            <h1 className="editorial-title">{displayFilename}</h1>
            <p className="text-gray-600 mt-1">
              Criado em {new Date(transcription.created_at).toLocaleString('pt-BR')}
            </p>
            {transcription.status === 'completed' && (
              <Link className="text-primary-700 hover:underline" to={`/meetings/${transcription.id}`}>
                Abrir reunião
              </Link>
            )}
            {transcription.status === 'failed' && <p role="alert" className="text-red-700 mt-2">
              {requestErrorMessage(500, transcription.error_message || 'Transcription processing failed')}
            </p>}
          </div>
        </div>
        
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={copyToClipboard} disabled={!canExportTranscript}>
            {copied ? <CheckCircle2 className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copied ? 'Copiado!' : 'Copiar'}
          </Button>
          <details className="relative">
            <summary className="btn-secondary cursor-pointer list-none gap-2">
              Exportar <ChevronDown className="h-4 w-4" aria-hidden="true" />
            </summary>
            <div className="absolute left-0 z-10 mt-2 grid min-w-36 rounded-xl border bg-surface p-2 shadow-popover sm:left-auto sm:right-0">
              {[
                ['TXT', downloadAsText],
                ['SRT', downloadAsSRT],
                ['VTT', downloadAsVTT],
                ['JSON', downloadAsJSON],
              ].map(([label, download]) => <button key={label} type="button" disabled={label !== 'JSON' && !canExportTranscript}
                onClick={download} className="min-h-11 rounded-lg px-3 text-left text-sm font-medium hover:bg-canvas disabled:text-muted">{label}</button>)}
            </div>
          </details>
        </div>
      </header>

      <dl aria-label="Informações da transcrição" className="flex flex-wrap gap-x-6 gap-y-2 border-b pb-4 text-[15px] text-gray-600">
        {[
          ['Duração', formatSeconds(transcription.duration_seconds)],
          ['Palavras', formatNumber(transcription.word_count ?? 0)],
          ['Falantes', formatNumber(transcription.num_speakers ?? 1)],
          ['Modelo', transcription.transcription_model === 'whisper' ? 'Faster-Whisper' : transcription.transcription_model === 'assemblyai' ? 'AssemblyAI' : 'Não informado'],
        ].map(([label, value]) => <div key={label} className="flex items-baseline gap-2">
          <dt>{label}</dt><dd className="font-semibold text-ink">{value}</dd>
        </div>)}
      </dl>

      <section aria-labelledby="complete-transcript-title">
        <h2 id="complete-transcript-title" className="text-[22px] font-semibold">Transcrição completa</h2>
        {transcription.status === 'completed' && Array.isArray(transcription.segments) && transcription.segments.length === 0
          ? <p className="mt-4 text-gray-600">Nenhuma fala foi identificada neste áudio.</p>
          : transcription.segments?.map((segment, index) => (
            <article key={index} className="editorial-segment">
              <time dateTime={`PT${segment.start}S`}>{formatSeconds(segment.start)} – {formatSeconds(segment.end)}</time>
              <div>
                <span className="editorial-speaker">Falante {segment.speaker?.replace('SPEAKER_', '')}</span>
                <p>{segment.text}</p>
              </div>
            </article>
          ))}
      </section>
    </div>
  )
}
