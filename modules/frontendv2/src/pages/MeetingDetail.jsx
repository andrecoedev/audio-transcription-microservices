import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import Button from '../components/Button'
import { audioService } from '../services/audioService'
import MeetingIntelligencePanel from '../components/MeetingIntelligencePanel'
import MeetingActionsPanel from '../components/MeetingActionsPanel'
import MeetingMinutesPanel from '../components/MeetingMinutesPanel'
import { formatCount, formatDuration, formatSeconds } from '../utils/format'
import { deletionFeedback } from '../utils/deletionFeedback'
import '../styles/editorial-workspace.css'

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
  const [mobileView, setMobileView] = useState('transcript')
  const [focusedSegment, setFocusedSegment] = useState(null)
  const [activeTab, setActiveTab] = useState('summary')
  const transcriptScrollRef = useRef(null)
  const tabRefs = useRef({})
  const initialHashMeeting = useRef(null)
  const loadedMeetingRef = useRef(null)
  const [intelligenceVersion, setIntelligenceVersion] = useState(0)
  const refreshActions = useCallback(() => setIntelligenceVersion(value => value + 1), [])
  const [minutesVersion, setMinutesVersion] = useState(0)
  const refreshMinutes = useCallback(() => setMinutesVersion(value => value + 1), [])

  const focusTab = useCallback(tabId => {
    tabRefs.current[tabId]?.focus()
    setActiveTab(tabId)
  }, [])

  const handleTabKeyDown = useCallback((event, currentIndex) => {
    let nextIndex
    if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % workspaceTabs.length
    else if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + workspaceTabs.length) % workspaceTabs.length
    else if (event.key === 'Home') nextIndex = 0
    else if (event.key === 'End') nextIndex = workspaceTabs.length - 1
    else return
    event.preventDefault()
    focusTab(workspaceTabs[nextIndex].id)
  }, [focusTab])

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
      const result = await audioService.deleteMeeting(id)
      toast.success(deletionFeedback('Reunião excluída', result.cleanup_pending))
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
    const behavior = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ? 'auto' : 'smooth'
    setFocusedSegment({ meetingId: id, segmentId })
    target.focus({ preventScroll: true })
    const mobile = window.matchMedia?.('(max-width: 860px)')?.matches
    if (mobile) target.scrollIntoView?.({ behavior, block: 'center' })
    else {
      container.scrollIntoView?.({ behavior: 'auto', block: 'nearest' })
      container.scrollTo?.({ top: Math.max(0, top), behavior })
    }
  }, [id])

  useEffect(() => {
    if (!transcript || loadedMeetingRef.current !== id || initialHashMeeting.current === id) return
    initialHashMeeting.current = id
    const order = window.location.hash.match(/^#segment-(\d+)$/)?.[1]
    if (order == null) return
    requestAnimationFrame(() => scrollToSegment(`segment-${order}`))
  }, [id, transcript, scrollToSegment])

  if (error) return <div className="space-y-3"><p role="alert">Não foi possível carregar esta reunião.</p><div className="flex gap-3"><Button variant="outline" onClick={load}>Tentar novamente</Button><Link className="inline-flex items-center text-sm text-primary-700 underline" to="/meetings">Voltar às reuniões</Link></div></div>
  if (!meeting || !transcript) return <p role="status">Carregando reunião...</p>

  const durationLabel = meeting.duration_seconds == null ? 'Duração não informada' : formatDuration(meeting.duration_seconds)

  return <div className="editorial-workspace">
    <header className="editorial-workspace-header">
      <div className="min-w-0 flex-1">
        <Link className="text-sm text-gray-500 hover:text-gray-900" to="/meetings">← Reuniões</Link>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <h1 className="editorial-title min-w-0 break-words">{meeting.title}</h1>
          {!editingTitle && <Button type="button" variant="outline" size="sm" onClick={() => setEditingTitle(true)}>Editar título</Button>}
        </div>
        {editingTitle && <form onSubmit={saveTitle} className="mt-2 flex flex-wrap items-center gap-2">
          <input aria-label="Título da reunião" required maxLength={255} value={title}
            onChange={event => setTitle(event.target.value)}
            className="min-w-[min(100%,24rem)] flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-lg font-medium text-gray-900" />
          <Button type="submit" size="sm">Salvar título</Button>
          <Button type="button" variant="outline" size="sm" onClick={() => { setTitle(meeting.title); setEditingTitle(false) }}>Cancelar</Button>
        </form>}
        <p className="mt-2 text-[15px] text-gray-500">{new Date(meeting.created_at).toLocaleString('pt-BR')} · {durationLabel} · {formatCount(meeting.speakers.length, 'falante', 'falantes')} · {formatCount(transcript.segments.length, 'trecho', 'trechos')}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {meeting.transcription_id && <Link to={`/transcriptions/${meeting.transcription_id}`} className="btn-secondary">Abrir transcrição</Link>}
        <details className="relative">
          <summary className="btn-secondary cursor-pointer list-none">Falantes</summary>
          <div className="editorial-speakers rounded-xl border border-gray-200 bg-surface p-4 shadow-popover">
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

    <div className="editorial-workspace-switch" role="group" aria-label="Visualização da reunião">
      <button type="button" aria-pressed={mobileView === 'transcript'} aria-controls="meeting-transcript" onClick={() => setMobileView('transcript')}>Transcrição</button>
      <button type="button" aria-pressed={mobileView === 'summary'} aria-controls="meeting-summary" onClick={() => setMobileView('summary')}>Resumo inteligente</button>
    </div>

    <div className="editorial-workspace-grid">
      <section id="meeting-transcript" aria-labelledby="meeting-transcript-title" className="editorial-transcript" data-mobile-active={mobileView === 'transcript'}>
        <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 id="meeting-transcript-title" className="text-[22px] font-semibold">Transcrição</h2>
          <label className="sr-only" htmlFor="transcript-search">Buscar na transcrição</label>
          <input id="transcript-search" type="search" value={query} onChange={event => setQuery(event.target.value)}
            placeholder="Buscar na transcrição" className="input max-w-56 rounded-full" />
        </header>
        <div ref={transcriptScrollRef} className="editorial-transcript-scroll" aria-label="Trechos da transcrição" role="region" tabIndex={0}>
          {segments.map(segment => {
            const segmentId = `segment-${segment.order}`
            return <article id={segmentId} key={segment.order} tabIndex={-1} className="editorial-segment"
              data-evidence={focusedSegment?.meetingId === id && focusedSegment.segmentId === segmentId}>
              <time dateTime={`PT${segment.start || 0}S`}>{formatSeconds(Number(segment.start || 0), 2)}</time>
              <div>
                <span className="editorial-speaker">{segment.speaker_display_name || segment.speaker || 'Falante'}</span>
                <p>{segment.text}</p>
              </div>
            </article>
          })}
          {segments.length === 0 && <p className="py-4 text-sm text-gray-500">{query.trim() ? 'Nenhum trecho corresponde à busca.' : meeting.status === 'completed' && Array.isArray(transcript.segments) ? 'Nenhuma fala foi identificada neste áudio.' : 'Nenhum trecho disponível nesta transcrição.'}</p>}
        </div>
        {query && <p className="pt-3 text-xs text-gray-500">{formatCount(segments.length, 'trecho', 'trechos')} de {formatCount(transcript.segments.length, 'trecho', 'trechos')}</p>}
      </section>

      <section id="meeting-summary" aria-labelledby="meeting-summary-title" className="editorial-summary" data-mobile-active={mobileView === 'summary'}>
        <h2 id="meeting-summary-title" className="mb-4 text-[22px] font-semibold">Resumo inteligente</h2>
        <div role="tablist" aria-label="Conteúdo da reunião" className="editorial-summary-tabs">
          {workspaceTabs.map((tab, index) => <button type="button" role="tab" id={`meeting-tab-${tab.id}`} key={tab.id} aria-selected={activeTab === tab.id}
            aria-controls="meeting-workspace-tab" tabIndex={activeTab === tab.id ? 0 : -1}
            ref={element => { tabRefs.current[tab.id] = element }}
            onKeyDown={event => handleTabKeyDown(event, index)} onClick={() => setActiveTab(tab.id)}
            >
            {tab.label}
          </button>)}
        </div>
        <div id="meeting-workspace-tab" role="tabpanel" aria-labelledby={`meeting-tab-${activeTab}`} tabIndex={0} className="editorial-summary-content"
          onClick={event => {
            const link = event.target.closest('a[href^="#segment-"]')
            if (!link) return
            event.preventDefault()
            const segmentId = link.getAttribute('href').slice(1)
            setQuery('')
            setMobileView('transcript')
            requestAnimationFrame(() => scrollToSegment(segmentId))
          }}>
          <div hidden={activeTab === 'actions'}>
            <MeetingIntelligencePanel key={id} meetingId={id} onResultChange={refreshActions} initialTab={activeTab} />
          </div>
          {activeTab === 'actions' && <MeetingActionsPanel key={id} meetingId={id} intelligenceVersion={intelligenceVersion} onActionsChanged={refreshMinutes} embedded />}
        </div>
      </section>
    </div>

    <details className="mt-8 border-t border-gray-200 pt-4">
      <summary className="cursor-pointer text-sm font-medium text-gray-700">Ata da reunião e exportação</summary>
      <div className="mt-3"><MeetingMinutesPanel key={`minutes-${id}`} meetingId={id} version={minutesVersion + intelligenceVersion} /></div>
    </details>
  </div>
}
