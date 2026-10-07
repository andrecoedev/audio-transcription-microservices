import { useEffect, useMemo, useState } from 'react'
import Card, { CardContent, CardHeader, CardTitle } from './Card'
import Button from './Button'
import { audioService } from '../services/audioService'
import { formatSeconds } from '../utils/format'

const emptyAction = { description: '', assignee: '', due_date: '' }
const statusLabels = { open: 'Aberta', done: 'Concluída', dismissed: 'Descartada' }

function payload(values) {
  return { description: values.description.trim(), assignee: values.assignee.trim() || null, due_date: values.due_date || null }
}

function EvidenceLinks({ evidence = [], references = [], evidenceBaseUrl = '' }) {
  if (!evidence.length) return <p className="text-sm text-gray-500">Sem evidência vinculada.</p>
  return <div className="text-sm text-gray-600">Evidência: {evidence.map((item, index) => {
    const reference = references.find(ref => ref.segment_order === item.segment_order)
    return <a key={`${item.segment_order}-${index}`} href={`${evidenceBaseUrl}#segment-${item.segment_order}`} title={item.quote || ''} className="text-primary-700 underline mr-3">
      {reference ? `${formatSeconds(reference.start)}–${formatSeconds(reference.end)}` : `Trecho ${item.segment_order + 1}`}
    </a>
  })}</div>
}

function ActionFields({ values, onChange, prefix }) {
  return <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
    <label className="flex min-w-0 flex-col gap-1 sm:col-span-2">Descrição
      <input aria-label={`${prefix} descrição`} required maxLength={4000} value={values.description}
        onChange={event => onChange({ ...values, description: event.target.value })} className="input h-10 min-w-0 mt-auto" />
    </label>
    <label className="flex min-w-0 flex-col gap-1">Responsável (opcional)
      <input aria-label={`${prefix} responsável`} maxLength={255} value={values.assignee}
        onChange={event => onChange({ ...values, assignee: event.target.value })} className="input h-10 min-w-0 mt-auto" />
    </label>
    <label className="flex min-w-0 flex-col gap-1">Prazo (opcional)
      <input aria-label={`${prefix} prazo`} type="date" value={values.due_date}
        onChange={event => onChange({ ...values, due_date: event.target.value })} className="input h-10 min-w-0 mt-auto" />
    </label>
  </div>
}

function ActionRow({ item, busy, change, remove, onViewOrigin, evidenceBaseUrl }) {
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
    <p className="text-sm text-gray-500">{item.source === 'ai_reviewed' ? 'IA → revisada' : 'Criada manualmente'} · {statusLabels[item.status]}</p>
    {editing ? <form onSubmit={save} className="space-y-3">
      <fieldset disabled={busy}><ActionFields values={values} onChange={setValues} prefix="Editar tarefa" /></fieldset>
      <div className="flex gap-2"><Button type="submit" disabled={busy || !values.description.trim()}>Salvar tarefa</Button>
        <Button type="button" variant="outline" disabled={busy} onClick={() => setEditing(false)}>Cancelar edição</Button></div>
    </form> : <>
      <p className="whitespace-pre-wrap">{item.description}</p>
      <p className="text-sm text-gray-600">Responsável: {item.assignee || 'Não definido'} · Prazo: {item.due_date || 'Sem prazo'}</p>
      {item.source === 'ai_reviewed' && <div className="space-y-1">
        <Button size="sm" variant="outline" disabled={busy} onClick={() => onViewOrigin(item)}>Ver sugestão original (revisão {item.source_revision})</Button>
        <EvidenceLinks evidence={item.evidence || []} evidenceBaseUrl={evidenceBaseUrl} />
      </div>}
      <div className="flex gap-2 flex-wrap">
        <Button size="sm" variant="outline" disabled={busy} onClick={edit}>Editar tarefa</Button>
        {item.status !== 'dismissed' && <Button size="sm" disabled={busy} onClick={() => change(item.id, { status: item.status === 'open' ? 'done' : 'open' })}>
          {item.status === 'open' ? 'Concluir' : 'Reabrir'}</Button>}
        {item.status === 'open' && <Button size="sm" variant="outline" disabled={busy} onClick={() => change(item.id, { status: 'dismissed' })}>Descartar</Button>}
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => remove(item.id)}>Excluir tarefa</Button>
      </div>
    </>}
  </li>
}

function Suggestion({ item, revision, references, busy, accept, dismiss, evidenceBaseUrl }) {
  const [editing, setEditing] = useState(false)
  const [values, setValues] = useState({ description: item.description || '', assignee: item.assignee || '', due_date: '' })
  const [expanded, setExpanded] = useState(false)

  async function acceptSuggestion(event) {
    event?.preventDefault()
    if (await accept(revision, item.source_index, editing ? payload(values) : {})) setEditing(false)
  }

  return <li className="p-4 border border-primary-100 bg-primary-50/50 rounded-lg space-y-3">
    <p className="text-xs uppercase tracking-wide text-gray-500">Sugestão da IA · revisão {revision}</p>
    {editing ? <form onSubmit={acceptSuggestion} className="space-y-3">
      <fieldset disabled={busy}><ActionFields values={values} onChange={setValues} prefix="Editar sugestão" /></fieldset>
      <div className="flex gap-2"><Button type="submit" disabled={busy || !values.description.trim()}>Aceitar tarefa revisada</Button>
        <Button type="button" variant="outline" disabled={busy} onClick={() => setEditing(false)}>Cancelar edição</Button></div>
    </form> : <>
      <p className="whitespace-pre-wrap">{item.description}</p>
      <p className="text-sm text-gray-600">Responsável: {item.assignee || 'Não identificado'} · Prazo indicado: {item.due_date || 'Sem prazo explícito'}</p>
      <EvidenceLinks evidence={item.evidence || []} references={references} evidenceBaseUrl={evidenceBaseUrl} />
      <div className="flex gap-2 flex-wrap">
        <Button size="sm" disabled={busy} onClick={() => acceptSuggestion()}>Aceitar</Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => setEditing(true)}>Editar e aceitar</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => dismiss(revision, item.source_index)}>Descartar sugestão</Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => setExpanded(value => !value)}>{expanded ? 'Ocultar origem' : 'Consultar revisão original'}</Button>
      </div>
      {expanded && <div className="border-l-2 border-primary-200 pl-3 text-sm">
        <p>Resultado original da IA, revisão {revision}. A aceitação não altera este registro.</p>
        <EvidenceLinks evidence={item.evidence || []} references={references} evidenceBaseUrl={evidenceBaseUrl} />
      </div>}
    </>}
  </li>
}

export default function MeetingActionsPanel({ meetingId, intelligenceVersion = 0, onActionsChanged, evidenceBaseUrl = '', embedded = false }) {
  const [items, setItems] = useState([])
  const [suggestionReviews, setSuggestionReviews] = useState([])
  const [suggestionResult, setSuggestionResult] = useState(null)
  const [values, setValues] = useState(emptyAction)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [origin, setOrigin] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([
      audioService.getMeetingActions(meetingId),
      audioService.getMeetingIntelligenceStatus(meetingId),
    ]).then(async ([actions, intelligence]) => {
      const latest = intelligence.completed_revision
        ? await audioService.getMeetingIntelligenceResult(meetingId, intelligence.completed_revision)
        : null
      if (!cancelled) { setItems(actions.action_items); setSuggestionReviews(actions.suggestion_reviews || []); setSuggestionResult(latest); setError('') }
    }).catch(() => {
      if (!cancelled) setError('Não foi possível carregar as tarefas e sugestões.')
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [meetingId, refresh, intelligenceVersion])

  const suggestions = useMemo(() => {
    const existing = new Set(items.filter(item => item.source_revision != null && item.source_index != null)
      .map(item => `${item.source_revision}:${item.source_index}`))
    const reviewed = new Set(suggestionReviews.map(item => `${item.source_revision}:${item.source_index}`))
    return (suggestionResult?.content?.action_items || []).map((item, source_index) => ({ ...item, source_index }))
      .filter(item => !existing.has(`${suggestionResult.revision}:${item.source_index}`)
        && !reviewed.has(`${suggestionResult.revision}:${item.source_index}`))
  }, [items, suggestionReviews, suggestionResult])

  async function mutate(operation) {
    setBusy(true)
    setError('')
    try {
      await operation()
      setRefresh(value => value + 1)
      onActionsChanged?.()
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

  const accept = (revision, sourceIndex, valuesToAccept) => mutate(() => audioService.acceptMeetingActionSuggestion(meetingId, revision, sourceIndex, valuesToAccept))
  const dismiss = (revision, sourceIndex) => mutate(() => audioService.dismissMeetingActionSuggestion(meetingId, revision, sourceIndex))

  async function viewOrigin(item) {
    setBusy(true)
    setError('')
    try {
      const result = await audioService.getMeetingIntelligenceResult(meetingId, item.source_revision)
      setOrigin({ item, result, source: result.content.action_items[item.source_index] })
    } catch { setError('Não foi possível consultar a revisão original da sugestão.') }
    finally { setBusy(false) }
  }

  const panelContent = <><CardHeader><CardTitle>Ações da reunião</CardTitle></CardHeader><CardContent>
    <div className="space-y-5">
      <p className="text-sm text-gray-600">Revise as sugestões da IA. As tarefas abaixo já foram confirmadas para esta reunião.</p>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {loading && <p role="status">Carregando tarefas e sugestões...</p>}
      <Button variant="outline" disabled={loading || busy} onClick={() => setRefresh(value => value + 1)}>Atualizar tarefas</Button>
      {!loading && !error && <section aria-labelledby="suggested-actions-heading" className="space-y-3">
        <h3 id="suggested-actions-heading" className="font-semibold">Sugeridas pela IA</h3>
        {!suggestionResult && <p className="text-sm text-gray-500">Ainda não há análise da reunião.</p>}
        {suggestionResult && suggestions.length === 0 && <p className="text-sm text-gray-500">Nenhuma sugestão pendente nesta revisão.</p>}
        <ul className="space-y-3">{suggestions.map(item => <Suggestion key={`${suggestionResult.revision}-${item.source_index}`} item={item}
          revision={suggestionResult.revision} references={suggestionResult.references || []} busy={busy} accept={accept} dismiss={dismiss} evidenceBaseUrl={evidenceBaseUrl} />)}</ul>
      </section>}
      {origin && <section className="p-4 border rounded-lg space-y-2" aria-label="Origem da tarefa">
        <div className="flex justify-between gap-3"><h3 className="font-semibold">Sugestão original · revisão {origin.item.source_revision}</h3>
          <Button size="sm" variant="ghost" onClick={() => setOrigin(null)}>Fechar origem</Button></div>
        <p>{origin.source?.description || origin.item.original_description}</p>
        <p className="text-sm text-gray-600">Responsável: {origin.source?.assignee || 'Não identificado'} · Prazo indicado: {origin.source?.due_date || 'Sem prazo explícito'}</p>
        <EvidenceLinks evidence={origin.source?.evidence || origin.item.evidence || []} references={origin.result.references || []} evidenceBaseUrl={evidenceBaseUrl} />
      </section>}
      <section aria-labelledby="operational-actions-heading" className="space-y-3">
        <h3 id="operational-actions-heading" className="font-semibold">Tarefas</h3>
        {!loading && !error && items.length === 0 && <p>Nenhuma tarefa criada.</p>}
        <ul className="space-y-3">{items.map(item => <ActionRow key={item.id} item={item} busy={busy || loading} change={change} remove={remove} onViewOrigin={viewOrigin} evidenceBaseUrl={evidenceBaseUrl} />)}</ul>
      </section>
      <form onSubmit={create} className="space-y-3">
        <h3 className="font-semibold">Criar tarefa manual</h3>
        <fieldset disabled={busy || loading}><ActionFields values={values} onChange={setValues} prefix="Nova tarefa" /></fieldset>
        <Button type="submit" disabled={busy || loading || !values.description.trim()}>{busy ? 'Salvando...' : 'Criar tarefa'}</Button>
      </form>
    </div>
  </CardContent></>
  return embedded ? <section className="space-y-4">{panelContent}</section> : <Card>{panelContent}</Card>
}
