import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import Button from '../components/Button'
import { audioService } from '../services/audioService'
import MeetingIntelligencePanel from '../components/MeetingIntelligencePanel'
import MeetingActionsPanel from '../components/MeetingActionsPanel'
import MeetingMinutesPanel from '../components/MeetingMinutesPanel'
import { formatCount, formatDuration, formatSeconds } from '../utils/format'

const workspaceTabs = [
  { id: 'summary', label: 'Resumo' },
  { id: 'topics', label: 'Tópicos' },
  { id: 'decisions', label: 'Decisões' },
  { id: 'actions', label: 'Tarefas' },
  { id: 'questions', label: 'Perguntas' },
]

export default function MeetingDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [meeting, setMeeting] = useState(null)
  const [transcript, setTranscript] = useState(null)
  const [title, setTitle] = useState('')
  const [editingTitle, setEditingTitle] = useState(false)
  const [speakerNames, setSpeakerNames] = useState({})
  const [error, setError] = useState(false)
  const [query, setQuery] = useState('')
  const [activeTab, setActiveTab] = useState('summary')
  const transcriptScrollRef = useRef(null)
  const initialHashMeeting = useRef(null)
  const loadedMeetingRef = useRef(null)
  const [intelligenceVersion, setIntelligenceVersion] = useState(0)
  const refreshActions = useCallback(() => setIntelligenceVersion(value => value + 1), [])
  const [minutesVersion, setMinutesVersion] = useState(0)
  const refreshMinutes = useCallback(() => setMinutesVersion(value => value + 1), [])

  const load = useCallback(async () => {
    try {
      const [item, result] = await Promise.all([audioService.getMeeting(id), audioService.getMeetingTranscript(id)])
      loadedMeetingRef.current = id
      setMeeting(item)
      setTitle(item.title)
      setSpeakerNames(Object.fromEntries(item.speakers.map(speaker => [speaker.id, speaker.display_name || ''])))
      setTranscript(result)
      setError(false)
    } catch {
      setError(true)
      toast.error('Erro ao carregar reunião')
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const saveTitle = async (event) => {
    event.preventDefault()
    try {
      await audioService.updateMeetingTitle(id, title.trim())
      toast.success('Título atualizado')
      setEditingTitle(false)
      await load()
    } catch { toast.error('Erro ao atualizar título') }
  }

  const saveSpeaker = async (event, speakerId) => {
    event.preventDefault()
    try {
      await audioService.renameMeetingSpeaker(id, speakerId, speakerNames[speakerId].trim())
      toast.success('Falante atualizado')
      await load()
    } catch { toast.error('Erro ao atualizar falante') }
  }

  const remove = async () => {
    if (!window.confirm('Excluir esta reunião e sua transcrição?')) return
    try {
      await audioService.deleteMeeting(id)
      toast.success('Reunião excluída')
      navigate('/meetings')
    } catch { toast.error('Erro ao excluir reunião') }
  }

  const segments = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('pt-BR')
    if (!normalizedQuery) return transcript?.segments || []
    return (transcript?.segments || []).filter(segment =>
      `${segment.text} ${segment.speaker_display_name || segment.speaker || ''}`.toLocaleLowerCase('pt-BR').includes(normalizedQuery))
  }, [query, transcript])

  const scrollToSegment = useCallback(segmentId => {
    const container = transcriptScrollRef.current
    const target = document.getElementById(segmentId)
    if (!container || !target) return
    const offset = target.getBoundingClientRect().top - container.getBoundingClientRect().top
    const top = container.scrollTop + offset - (container.clientHeight - target.offsetHeight) / 2
    container.scrollTo?.({ top: Math.max(0, top), behavior: 'smooth' })
  }, [])

  useEffect(() => {
    if (!transcript || loadedMeetingRef.current !== id || initialHashMeeting.current === id) return
    initialHashMeeting.current = id
    const order = window.location.hash.match(/^#segment-(\d+)$/)?.[1]
    if (order == null) return
    requestAnimationFrame(() => scrollToSegment(`segment-${order}`))
  }, [id, transcript, scrollToSegment])

  if (error) return <p role="alert">Reunião indisponível. <Link to="/meetings">Voltar</Link></p>
  if (!meeting || !transcript) return <p role="status">Carregando reunião...</p>

  const durationLabel = meeting.duration_seconds == null ? 'Duração não informada' : formatDuration(meeting.duration_seconds)

  return <div className="space-y-5">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 flex-1">
        <Link className="text-sm text-gray-500 hover:text-gray-900" to="/meetings">← Reuniões</Link>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <h1 className="min-w-0 break-words text-3xl font-semibold tracking-tight text-gray-900">{meeting.title}</h1>
          {!editingTitle && <Button type="button" variant="outline" size="sm" onClick={() => setEditingTitle(true)}>Editar título</Button>}
        </div>
        {editingTitle && <form onSubmit={saveTitle} className="mt-2 flex flex-wrap items-center gap-2">
          <input aria-label="Título da reunião" required maxLength={255} value={title}
            onChange={event => setTitle(event.target.value)}
            className="min-w-[min(100%,24rem)] flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-lg font-medium text-gray-900" />
          <Button type="submit" size="sm">Salvar título</Button>
          <Button type="button" variant="outline" size="sm" onClick={() => { setTitle(meeting.title); setEditingTitle(false) }}>Cancelar</Button>
        </form>}
        <p className="mt-1 text-sm text-gray-500">{new Date(meeting.created_at).toLocaleString('pt-BR')} · {durationLabel} · {formatCount(meeting.speakers.length, 'falante', 'falantes')}</p>
      </div>
      <div className="flex items-center gap-2">
        {meeting.transcription_id && <Link to={`/transcriptions/${meeting.transcription_id}`} className="inline-flex items-center rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Exportar transcrição</Link>}
        <details className="relative">
          <summary className="cursor-pointer list-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700">Falantes</summary>
          <div className="absolute right-0 z-10 mt-2 w-[min(24rem,90vw)] rounded-xl border border-gray-200 bg-white p-4 shadow-lg">
            <h2 className="mb-3 font-semibold">Renomear falantes</h2>
            {meeting.speakers.length === 0 ? <p className="text-sm text-gray-500">Nenhum falante identificado.</p> : <div className="space-y-3">
              {meeting.speakers.map(speaker => <form key={speaker.id} onSubmit={event => saveSpeaker(event, speaker.id)} className="flex items-center gap-2">
                <label htmlFor={`speaker-${speaker.id}`} className="w-20 shrink-0 text-sm text-gray-600">{speaker.id}</label>
                <input id={`speaker-${speaker.id}`} aria-label={`Nome de ${speaker.id}`} required maxLength={100}
                  value={speakerNames[speaker.id] || ''} onChange={event => setSpeakerNames({ ...speakerNames, [speaker.id]: event.target.value })}
                  className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                <Button type="submit" size="sm" variant="outline">Renomear</Button>
              </form>)}
            </div>}
          </div>
        </details>
        <Button variant="outline" onClick={remove}>Excluir reunião</Button>
      </div>
    </header>

    <div className="grid min-h-0 gap-5 xl:h-[min(72vh,52rem)] xl:grid-cols-[minmax(0,1.65fr)_minmax(20rem,0.9fr)]">
      <Card className="!p-0 flex h-[65vh] min-h-[28rem] flex-col overflow-hidden xl:h-full">
        <CardHeader className="border-b border-gray-200 px-5 pt-5 pb-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><CardTitle>Transcrição</CardTitle><p className="mt-1 text-sm text-gray-500">{formatCount(transcript.segments.length, 'trecho', 'trechos')} · {durationLabel} · {formatCount(meeting.speakers.length, 'falante', 'falantes')}</p></div>
            <label className="sr-only" htmlFor="transcript-search">Buscar no áudio</label>
            <input id="transcript-search" type="search" value={query} onChange={event => setQuery(event.target.value)}
              placeholder="Buscar no áudio" className="w-full max-w-xs rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm" />
          </div>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col p-0">
          <div ref={transcriptScrollRef} className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain px-5 py-4" aria-label="Trechos da transcrição">
            {segments.map(segment => <article id={`segment-${segment.order}`} key={segment.order} className="rounded-lg px-3 py-3 hover:bg-gray-50">
              <div className="mb-1 flex items-center gap-2 text-sm">
                <span className="rounded-full bg-primary-50 px-2.5 py-1 font-medium text-primary-700">{segment.speaker_display_name || segment.speaker || 'Falante'}</span>
                <time className="text-gray-500" dateTime={`PT${segment.start || 0}S`}>{formatSeconds(Number(segment.start || 0), 2)}</time>
              </div>
              <p className="whitespace-pre-wrap leading-7 text-gray-900">{segment.text}</p>
            </article>)}
            {segments.length === 0 && <p className="p-4 text-sm text-gray-500">{query ? 'Nenhum trecho corresponde à busca.' : 'Nenhum trecho disponível.'}</p>}
          </div>
          <footer className="flex justify-between border-t border-gray-200 px-5 py-3 text-xs text-gray-500">
            <span>{query ? `${formatCount(segments.length, 'trecho', 'trechos')} de ${formatCount(transcript.segments.length, 'trecho', 'trechos')}` : `${formatCount(segments.length, 'trecho', 'trechos')} · role para continuar`}</span>
            <span>{durationLabel}</span>
          </footer>
        </CardContent>
      </Card>

      <Card className="!p-0 flex h-[65vh] min-h-[28rem] flex-col overflow-hidden xl:h-full">
        <CardHeader className="px-5 pt-5 pb-3"><div className="flex items-center justify-between gap-2"><CardTitle>Resumo inteligente</CardTitle><span className="rounded-full bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-700">{formatCount(transcript.segments.length, 'fala', 'falas')}</span></div></CardHeader>
        <div role="tablist" aria-label="Conteúdo da reunião" className="flex gap-1 overflow-x-auto border-b border-gray-200 px-4">
          {workspaceTabs.map(tab => <button type="button" role="tab" key={tab.id} aria-selected={activeTab === tab.id}
            aria-controls="meeting-workspace-tab" onClick={() => setActiveTab(tab.id)}
            className={`shrink-0 rounded-t-lg px-3 py-2 text-sm ${activeTab === tab.id ? 'bg-primary-50 font-medium text-primary-700' : 'text-gray-600 hover:bg-gray-50'}`}>
            {tab.label}
          </button>)}
        </div>
        <div id="meeting-workspace-tab" role="tabpanel" className="min-h-0 flex-1 overflow-y-auto p-4"
          onClick={event => {
            const link = event.target.closest('a[href^="#segment-"]')
            if (!link) return
            event.preventDefault()
            const segmentId = link.getAttribute('href').slice(1)
            setQuery('')
            requestAnimationFrame(() => scrollToSegment(segmentId))
          }}>
          <div hidden={activeTab === 'actions'}>
            <MeetingIntelligencePanel key={id} meetingId={id} onResultChange={refreshActions} initialTab={activeTab} />
          </div>
          {activeTab === 'actions' && <MeetingActionsPanel key={id} meetingId={id} intelligenceVersion={intelligenceVersion} onActionsChanged={refreshMinutes} embedded />}
        </div>
      </Card>
    </div>

    <details className="group">
      <summary className="cursor-pointer text-sm font-medium text-gray-700">Ata da reunião e exportação</summary>
      <div className="mt-3"><MeetingMinutesPanel key={`minutes-${id}`} meetingId={id} version={minutesVersion + intelligenceVersion} /></div>
    </details>
  </div>
}
