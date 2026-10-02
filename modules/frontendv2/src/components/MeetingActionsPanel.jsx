import { useEffect, useState } from 'react'
import Card, { CardContent, CardHeader, CardTitle } from './Card'
import Button from './Button'
import { audioService } from '../services/audioService'

function ActionFields({ values, onChange, prefix }) {
  return <div className="grid gap-3 md:grid-cols-3">
    <label className="md:col-span-3">Descrição
      <input aria-label={`${prefix} descrição`} required maxLength={4000} value={values.description}
        onChange={event => onChange({ ...values, description: event.target.value })} className="block w-full border rounded-lg px-3 py-2" />
    </label>
    <label>Responsável (opcional)
      <input aria-label={`${prefix} responsável`} maxLength={255} value={values.assignee}
        onChange={event => onChange({ ...values, assignee: event.target.value })} className="block w-full border rounded-lg px-3 py-2" />
    </label>
    <label>Prazo (opcional)
      <input aria-label={`${prefix} prazo`} type="date" value={values.due_date}
        onChange={event => onChange({ ...values, due_date: event.target.value })} className="block w-full border rounded-lg px-3 py-2" />
    </label>
  </div>
}

const emptyAction = { description: '', assignee: '', due_date: '' }
const statusLabels = { open: 'Aberta', done: 'Concluída', dismissed: 'Descartada' }

function payload(values) {
  return { description: values.description.trim(), assignee: values.assignee.trim() || null, due_date: values.due_date || null }
}

function ActionRow({ item, busy, change, remove }) {
  const [editing, setEditing] = useState(false)
  const [values, setValues] = useState(emptyAction)

  function edit() {
    setValues({ description: item.description, assignee: item.assignee || '', due_date: item.due_date || '' })
    setEditing(true)
  }

  async function save(event) {
    event.preventDefault()
    if (await change(item.id, payload(values))) setEditing(false)
  }

  return <li className="p-4 bg-gray-50 rounded-lg space-y-3">
    <p className="text-sm text-gray-500">Criada manualmente · {statusLabels[item.status]}</p>
    {editing ? <form onSubmit={save} className="space-y-3">
      <fieldset disabled={busy}><ActionFields values={values} onChange={setValues} prefix="Editar tarefa" /></fieldset>
      <div className="flex gap-2"><Button type="submit" disabled={busy || !values.description.trim()}>Salvar tarefa</Button>
        <Button type="button" variant="outline" disabled={busy} onClick={() => setEditing(false)}>Cancelar edição</Button></div>
    </form> : <>
      <p className="whitespace-pre-wrap">{item.description}</p>
      <p className="text-sm text-gray-600">Responsável: {item.assignee || 'Não definido'} · Prazo: {item.due_date || 'Sem prazo'}</p>
      <div className="flex gap-2 flex-wrap">
        <Button size="sm" variant="outline" disabled={busy} onClick={edit}>Editar tarefa</Button>
        <Button size="sm" disabled={busy} onClick={() => change(item.id, { status: item.status === 'open' ? 'done' : 'open' })}>
          {item.status === 'open' ? 'Concluir' : 'Reabrir'}</Button>
        {item.status !== 'dismissed' && <Button size="sm" variant="outline" disabled={busy} onClick={() => change(item.id, { status: 'dismissed' })}>Descartar</Button>}
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => remove(item.id)}>Excluir tarefa</Button>
      </div>
    </>}
  </li>
}

export default function MeetingActionsPanel({ meetingId }) {
  const [items, setItems] = useState([])
  const [values, setValues] = useState(emptyAction)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    audioService.getMeetingActions(meetingId).then(result => {
      if (!cancelled) { setItems(result.action_items); setError('') }
    }).catch(() => {
      if (!cancelled) setError('Não foi possível carregar as tarefas.')
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [meetingId, refresh])

  async function mutate(operation) {
    setBusy(true)
    setError('')
    try {
      await operation()
      setRefresh(value => value + 1)
      return true
    } catch {
      setError('Não foi possível salvar a alteração. Tente novamente.')
      return false
    } finally { setBusy(false) }
  }

  async function create(event) {
    event.preventDefault()
    if (await mutate(() => audioService.createMeetingAction(meetingId, payload(values)))) setValues(emptyAction)
  }

  const change = (actionId, changes) => mutate(() => audioService.updateMeetingAction(meetingId, actionId, changes))
  function remove(actionId) {
    if (window.confirm('Excluir esta tarefa permanentemente? Para manter o registro, use Descartar.')) {
      return mutate(() => audioService.deleteMeetingAction(meetingId, actionId))
    }
  }

  return <Card><CardHeader><CardTitle>Ações da reunião</CardTitle></CardHeader><CardContent>
    <div className="space-y-4">
      <p className="text-sm text-gray-600">Tarefas administradas por você, independentes do resultado da IA.</p>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {loading && <p role="status">Carregando tarefas...</p>}
      <Button variant="outline" disabled={loading || busy} onClick={() => setRefresh(value => value + 1)}>Atualizar tarefas</Button>
      {!loading && !error && items.length === 0 && <p>Nenhuma tarefa criada.</p>}
      <ul className="space-y-3">{items.map(item => <ActionRow key={item.id} item={item} busy={busy || loading} change={change} remove={remove} />)}</ul>
      <form onSubmit={create} className="space-y-3">
        <h3 className="font-semibold">Criar tarefa manual</h3>
        <fieldset disabled={busy || loading}><ActionFields values={values} onChange={setValues} prefix="Nova tarefa" /></fieldset>
        <Button type="submit" disabled={busy || loading || !values.description.trim()}>{busy ? 'Salvando...' : 'Criar tarefa'}</Button>
      </form>
    </div>
  </CardContent></Card>
}
