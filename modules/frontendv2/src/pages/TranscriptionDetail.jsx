import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { 
  ArrowLeft, 
  Download, 
  FileAudio,
  Clock,
  User,
  FileText,
  Copy,
  CheckCircle2
} from 'lucide-react'
import Card, { CardHeader, CardTitle, CardContent } from '../components/Card'
import Button from '../components/Button'
import ProcessingStatus from '../components/ProcessingStatus'
import PageHeader from '../components/PageHeader'
import { audioService } from '../services/audioService'
import { requestErrorMessage } from '../services/requestError'
import { formatDuration, formatNumber, formatSeconds, getDisplayFilename } from '../utils/format'
import toast from 'react-hot-toast'

export default function TranscriptionDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [transcription, setTranscription] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [copied, setCopied] = useState(false)
  const displayFilename = getDisplayFilename(transcription)
  const canExportTranscript = transcription?.status === 'completed' && Boolean(transcription?.segments?.length)

  const loadTranscription = useCallback(async ({ silent = false } = {}) => {
    try {
      if (!silent) setLoading(true)
      const data = await audioService.getTranscription(id)
      setTranscription(data)
      setLoadError(false)
    } catch {
      if (!silent) setLoadError(true)
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
        <Link to="/transcriptions">
          <Button variant="primary" className="mt-4">Voltar para Transcrições</Button>
        </Link>
      </div>
    )
  }

  if (['queued', 'processing'].includes(transcription.status)) {
    return <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="Transcrevendo áudio" description={`${displayFilename} · ${formatDuration(transcription.duration_seconds)}`} />
      <ProcessingStatus status={transcription.status} />
      <Link to="/transcriptions" className="inline-flex items-center text-sm font-medium text-gray-600 hover:text-gray-900">
        <ArrowLeft className="mr-2 h-4 w-4" />Voltar ao histórico
      </Link>
    </div>
  }

  return (
    <div className="mx-auto min-w-0 max-w-6xl space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-start gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/transcriptions')}
            icon={ArrowLeft}
          >
            Voltar
          </Button>
          <div className="min-w-0">
            <h1 className="break-all text-3xl font-bold text-gray-900">{displayFilename}</h1>
            <p className="text-gray-600 mt-1">
              Criado em {new Date(transcription.created_at).toLocaleString('pt-BR')}
            </p>
            {['queued', 'processing'].includes(transcription.status) && <div className="mt-4 max-w-md"><ProcessingStatus status={transcription.status} /></div>}
            {transcription.status === 'completed' && (
              <Link className="text-primary-700 hover:underline" to={`/meetings/${transcription.id}`}>
                Ver reunião estruturada
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
          <Button variant="outline" size="sm" onClick={downloadAsText} disabled={!canExportTranscript}>
            <Download className="w-4 h-4" />
            TXT
          </Button>
          <Button variant="outline" size="sm" onClick={downloadAsJSON}>
            <Download className="w-4 h-4" />
            JSON
          </Button>
          <Button variant="outline" size="sm" onClick={downloadAsVTT} disabled={!canExportTranscript}>
            <Download className="w-4 h-4" />
            VTT
          </Button>
          <Button variant="outline" size="sm" onClick={downloadAsSRT} disabled={!canExportTranscript}>
            <Download className="w-4 h-4" />
            SRT
          </Button>
        </div>
      </div>

      {/* Estatísticas */}
      <div aria-label="Informações da transcrição" className="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={Clock}
          label="Duração"
          value={formatSeconds(transcription.duration_seconds)}
        />
        <StatCard
          icon={FileText}
          label="Palavras"
          value={formatNumber(transcription.word_count ?? 0)}
        />
        <StatCard
          icon={User}
          label="Falantes"
          value={formatNumber(transcription.num_speakers ?? 1)}
        />
        <StatCard
          icon={FileAudio}
          label="Modelo"
          value={transcription.transcription_model === 'whisper' ? 'Faster-Whisper' : transcription.transcription_model === 'assemblyai' ? 'AssemblyAI' : 'Não informado'}
        />
      </div>

      {/* Transcrição */}
      <Card>
        <CardHeader>
          <CardTitle>Transcrição completa</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {transcription.segments?.map((segment, index) => (
              <div
                key={index}
                className="p-4 bg-gray-50 rounded-lg border border-gray-200"
              >
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-primary-100 text-primary-700 text-sm font-medium">
                      {segment.speaker?.replace('SPEAKER_', '')}
                    </span>
                    <span className="font-medium text-gray-900">
                      Falante {segment.speaker?.replace('SPEAKER_', '')}
                    </span>
                  </div>
                  <span className="text-sm text-gray-500">
                    {formatSeconds(segment.start)} - {formatSeconds(segment.end)}
                  </span>
                </div>
                <p className="break-words text-gray-800 leading-relaxed">{segment.text}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function StatCard({ icon: Icon, label, value }) {
  return (
    <Card className="min-w-0">
      <div className="flex min-w-0 items-center gap-3">
        <div className="shrink-0 p-3 rounded-lg bg-primary-100">
          <Icon className="w-5 h-5 text-primary-600" />
        </div>
        <div className="min-w-0">
          <p className="text-sm text-gray-600">{label}</p>
          <p className="break-words text-xl font-bold text-gray-900">{value}</p>
        </div>
      </div>
    </Card>
  )
}
