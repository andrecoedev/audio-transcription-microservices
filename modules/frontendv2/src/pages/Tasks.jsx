import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Button from '../components/Button'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import MeetingActionsPanel from '../components/MeetingActionsPanel'
import { audioService } from '../services/audioService'
import { formatCount, formatNumber } from '../utils/format'

const limit = 20

export default function Tasks() {
  const [meetings, setMeetings] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [skip, setSkip] = useState(0)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const result = await audioService.listMeetings({ skip, limit })
      setMeetings(result.meetings)
      setTotal(result.total ?? result.meetings.length)
      setSelectedId(current => result.meetings.some(item => String(item.id) === current) ? current : '')
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [skip])

  useEffect(() => { load() }, [load])

  const page = Math.floor(skip / limit) + 1
  return <div className="space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-3xl font-semibold tracking-tight text-gray-900">Tarefas</h1>
        <p className="mt-1 text-gray-600">Revise as sugestões e acompanhe tarefas de uma reunião.</p></div>
    </header>

    <Card>
      <CardHeader><CardTitle>Escolha uma reunião</CardTitle></CardHeader>
      <CardContent>
        {loading ? <p role="status" className="text-sm text-gray-500">Carregando reuniões...</p> : error ? <div className="space-y-3">
          <p role="alert" className="text-sm text-red-700">Não foi possível carregar as reuniões.</p>
          <Button variant="outline" onClick={load}>Tentar novamente</Button>
        </div> : meetings.length === 0 ? <p className="text-sm text-gray-500">Nenhuma reunião disponível.</p> : <>
          <label htmlFor="task-meeting" className="mb-2 block text-sm font-medium text-gray-700">Reunião</label>
          <select id="task-meeting" value={selectedId} onChange={event => setSelectedId(event.target.value)}
            className="w-full max-w-2xl rounded-lg border border-gray-300 bg-white px-3 py-2">
            <option value="">Selecione uma reunião</option>
            {meetings.map(meeting => <option key={meeting.id} value={meeting.id}>{meeting.title} · {new Date(meeting.created_at).toLocaleDateString('pt-BR')}</option>)}
          </select>
          <div className="mt-4 flex items-center justify-between gap-3">
            <Button variant="outline" disabled={skip === 0} onClick={() => setSkip(value => Math.max(0, value - limit))}>Anterior</Button>
            <p className="text-sm text-gray-500">Página {formatNumber(page)} · {formatCount(total, 'reunião', 'reuniões')}</p>
            <Button variant="outline" disabled={skip + limit >= total} onClick={() => setSkip(value => value + limit)}>Próxima</Button>
          </div>
        </>}
      </CardContent>
    </Card>

    {selectedId && <section aria-label="Tarefas da reunião selecionada" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="min-w-0 break-words text-xl font-semibold">{meetings.find(item => String(item.id) === selectedId)?.title}</h2>
        <Link className="text-sm text-[#31594b] underline" to={`/meetings/${selectedId}`}>Abrir reunião completa</Link>
      </div>
      <MeetingActionsPanel key={selectedId} meetingId={selectedId} evidenceBaseUrl={`/meetings/${selectedId}`} />
    </section>}
  </div>
}
