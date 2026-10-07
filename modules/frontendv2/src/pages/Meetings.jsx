import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import Button from '../components/Button'
import { audioService } from '../services/audioService'
import { formatCount, formatDuration, formatNumber, formatTimestamp } from '../utils/format'

export default function Meetings() {
  const [meetings, setMeetings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [total, setTotal] = useState(0)
  const [skip, setSkip] = useState(0)
  const limit = 20

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const result = await audioService.listMeetings({ skip, limit })
      setMeetings(result.meetings || [])
      setTotal(result.total ?? result.meetings?.length ?? 0)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [skip])

  useEffect(() => { load() }, [load])

  const remove = async (meeting) => {
    if (!window.confirm(`Excluir a reunião “${meeting.title}” e sua transcrição?`)) return
    try {
      await audioService.deleteMeeting(meeting.id)
      await load()
    } catch {
      setError(true)
    }
  }

  return <div className="space-y-6">
    <header><h1 className="text-3xl font-bold text-gray-900">Reuniões</h1><p className="mt-1 text-gray-600">Transcrições concluídas e reuniões salvas.</p></header>
    <Card className="overflow-hidden p-0"><CardHeader className="px-5 pt-5"><CardTitle>Reuniões</CardTitle></CardHeader><CardContent>
      {loading ? <p role="status" className="p-8 text-center text-gray-600">Carregando reuniões...</p> : error ? <div className="space-y-3 p-5"><p role="alert">Não foi possível atualizar a lista de reuniões.</p><Button onClick={load}>Tentar novamente</Button></div> : meetings.length === 0 ? <p className="p-8 text-center text-gray-600">Nenhuma reunião nesta página.</p> :
        <div className="overflow-x-auto"><table className="w-full min-w-[700px] text-left text-sm"><thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500"><tr><th className="px-4 py-3">Reunião</th><th className="px-4 py-3">Data</th><th className="px-4 py-3">Duração</th><th className="px-4 py-3">Falantes</th><th className="px-4 py-3">Status</th><th className="px-4 py-3 text-right">Ações</th></tr></thead><tbody className="divide-y divide-gray-200">{meetings.map((meeting) => <tr key={meeting.id} className="hover:bg-gray-50">
          <td className="max-w-xs truncate px-4 py-4"><Link className="font-medium text-gray-900 hover:underline" to={`/meetings/${meeting.id}`}>{meeting.title}</Link></td>
          <td className="whitespace-nowrap px-4 py-4 text-gray-600">{formatTimestamp(meeting.created_at)}</td>
          <td className="whitespace-nowrap px-4 py-4 text-gray-600">{formatDuration(meeting.duration_seconds)}</td>
          <td className="px-4 py-4 text-gray-600">{formatCount(meeting.speaker_count, 'falante', 'falantes')}</td>
          <td className="px-4 py-4"><span className="rounded-full bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-800">{meeting.status === 'completed' ? 'Concluída' : meeting.status}</span></td>
          <td className="px-4 py-4 text-right"><Button variant="ghost" size="sm" onClick={() => remove(meeting)}>Excluir</Button></td>
        </tr>)}</tbody></table></div>}
    </CardContent></Card>
    {!error && <div className="flex items-center justify-between gap-3"><Button variant="outline" disabled={loading || skip === 0} onClick={() => setSkip((value) => Math.max(0, value - limit))}>Anterior</Button><p className="text-sm text-gray-600">Página {formatNumber(Math.floor(skip / limit) + 1)} · {formatCount(total, 'reunião', 'reuniões')}</p><Button variant="outline" disabled={loading || skip + limit >= total} onClick={() => setSkip((value) => value + limit)}>Próxima</Button></div>}
  </div>
}
