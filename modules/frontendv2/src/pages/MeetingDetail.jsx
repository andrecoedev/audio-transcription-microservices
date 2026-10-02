import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import Button from '../components/Button'
import { audioService } from '../services/audioService'
import MeetingIntelligencePanel from '../components/MeetingIntelligencePanel'
import MeetingActionsPanel from '../components/MeetingActionsPanel'
import MeetingMinutesPanel from '../components/MeetingMinutesPanel'

export default function MeetingDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [meeting, setMeeting] = useState(null)
  const [transcript, setTranscript] = useState(null)
  const [title, setTitle] = useState('')
  const [speakerNames, setSpeakerNames] = useState({})
  const [error, setError] = useState(false)
  const [intelligenceVersion, setIntelligenceVersion] = useState(0)
  const refreshActions = useCallback(() => setIntelligenceVersion(value => value + 1), [])
  const [minutesVersion, setMinutesVersion] = useState(0)
  const refreshMinutes = useCallback(() => setMinutesVersion(value => value + 1), [])

  const load = useCallback(async () => {
    try {
      const [item, result] = await Promise.all([audioService.getMeeting(id), audioService.getMeetingTranscript(id)])
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

  if (error) return <p>Reunião indisponível. <Link to="/meetings">Voltar</Link></p>
  if (!meeting || !transcript) return <p>Carregando reunião...</p>

  return <div className="space-y-6">
    <div className="flex justify-between gap-4"><div><Link className="text-primary-700" to="/meetings">← Reuniões</Link><h1 className="text-3xl font-bold text-gray-900">{meeting.title}</h1>
      <p className="text-gray-600">{new Date(meeting.created_at).toLocaleString('pt-BR')} · {meeting.duration_seconds?.toFixed(1) ?? '—'}s · {meeting.language || 'Idioma não detectado'} · {meeting.status === 'completed' ? 'Concluída' : meeting.status}</p></div>
      <Button variant="ghost" onClick={remove}>Excluir</Button></div>
    <Card><CardHeader><CardTitle>Título</CardTitle></CardHeader><CardContent><form onSubmit={saveTitle} className="flex gap-3">
      <input aria-label="Título da reunião" required maxLength={255} value={title} onChange={event => setTitle(event.target.value)} className="flex-1 px-3 py-2 border rounded-lg" />
      <Button type="submit">Salvar</Button></form></CardContent></Card>
    <Card><CardHeader><CardTitle>Falantes</CardTitle></CardHeader><CardContent><div className="space-y-3">
      {meeting.speakers.length === 0 ? <p>Nenhum falante identificado.</p> : meeting.speakers.map(speaker => <form key={speaker.id} onSubmit={event => saveSpeaker(event, speaker.id)} className="flex items-center gap-3">
        <label htmlFor={`speaker-${speaker.id}`} className="w-32 text-sm">{speaker.id}</label>
        <input id={`speaker-${speaker.id}`} aria-label={`Nome de ${speaker.id}`} required maxLength={100} value={speakerNames[speaker.id] || ''} onChange={event => setSpeakerNames({ ...speakerNames, [speaker.id]: event.target.value })} className="flex-1 px-3 py-2 border rounded-lg" />
        <Button type="submit" size="sm">Renomear</Button>
      </form>)}</div></CardContent></Card>
    <MeetingIntelligencePanel meetingId={id} onResultChange={refreshActions} />
    <MeetingActionsPanel key={id} meetingId={id} intelligenceVersion={intelligenceVersion} onActionsChanged={refreshMinutes} />
    <MeetingMinutesPanel key={`minutes-${id}`} meetingId={id} version={minutesVersion + intelligenceVersion} />
    <Card><CardHeader><CardTitle>Transcrição</CardTitle></CardHeader><CardContent><div className="space-y-4">
      {transcript.segments.map(segment => <div id={`segment-${segment.order}`} key={segment.order} className="p-4 bg-gray-50 rounded-lg border border-gray-200">
        <div className="flex justify-between text-sm text-gray-600"><span>{segment.speaker_display_name || segment.speaker || 'Falante'}</span><span>{segment.start?.toFixed(1)}s – {segment.end?.toFixed(1)}s</span></div>
        <p className="text-gray-800 mt-2">{segment.text}</p>
      </div>)}</div></CardContent></Card>
  </div>
}
