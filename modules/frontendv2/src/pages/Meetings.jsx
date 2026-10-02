import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import Button from '../components/Button'
import { audioService } from '../services/audioService'

export default function Meetings() {
  const [meetings, setMeetings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [total, setTotal] = useState(0)
  const [skip, setSkip] = useState(0)
  const limit = 20

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setError(false)
      const result = await audioService.listMeetings({ skip, limit })
      setMeetings(result.meetings)
      setTotal(result.total ?? result.meetings.length)
    } catch {
      setError(true)
      toast.error('Erro ao carregar reuniões')
    } finally {
      setLoading(false)
    }
  }, [skip])

  useEffect(() => { load() }, [load])

  const remove = async (meeting) => {
    if (!window.confirm(`Excluir a reunião ${meeting.title} e sua transcrição?`)) return
    try {
      await audioService.deleteMeeting(meeting.id)
      toast.success('Reunião excluída')
      await load()
    } catch {
      toast.error('Erro ao excluir reunião')
    }
  }

  return <div className="space-y-6">
    <div><h1 className="text-3xl font-bold text-gray-900">Reuniões</h1><p className="text-gray-600 mt-1">Resultados processados e persistidos</p></div>
    <Card><CardHeader><CardTitle>Reuniões processadas</CardTitle></CardHeader><CardContent>
      {loading ? <p>Carregando reuniões...</p> : error ? <div className="space-y-3">
        <p role="alert">Não foi possível carregar as reuniões.</p><Button onClick={load}>Tentar novamente</Button>
      </div> : meetings.length === 0 ? <p>Nenhuma reunião nesta página.</p> :
        <div className="space-y-3">{meetings.map(meeting => <div key={meeting.id} className="p-4 border border-gray-200 rounded-lg flex items-center justify-between gap-4">
          <div><Link className="font-medium text-primary-700 hover:underline" to={`/meetings/${meeting.id}`}>{meeting.title}</Link>
            <p className="text-sm text-gray-500">{new Date(meeting.created_at).toLocaleString('pt-BR')} · {meeting.duration_seconds?.toFixed(1) ?? '—'}s · {meeting.speaker_count} falante(s) · {meeting.status === 'completed' ? 'Concluída' : meeting.status}</p></div>
          <Button variant="ghost" size="sm" onClick={() => remove(meeting)}>Excluir</Button>
        </div>)}</div>}
    </CardContent></Card>
    {!error && <div className="flex items-center justify-between gap-3">
      <Button variant="outline" disabled={loading || skip === 0} onClick={() => setSkip(value => Math.max(0, value - limit))}>Anterior</Button>
      <p>Página {Math.floor(skip / limit) + 1} · {total} reuniões</p>
      <Button variant="outline" disabled={loading || skip + limit >= total} onClick={() => setSkip(value => value + limit)}>Próxima</Button>
    </div>}
  </div>
}
