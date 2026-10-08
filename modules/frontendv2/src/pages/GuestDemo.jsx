import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Button from '../components/Button'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import PageHeader from '../components/PageHeader'
import { guestService } from '../services/guestService'
import { formatDuration, formatSeconds } from '../utils/format'

const RETURN_TO = encodeURIComponent('/new-transcription')

export default function GuestDemo() {
  const [demo, setDemo] = useState(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const [speaker, setSpeaker] = useState('all')
  const [tab, setTab] = useState('transcript')
  const [focusedOrder, setFocusedOrder] = useState(null)
  const segmentRefs = useRef({})

  useEffect(() => {
    let active = true
    setError('')
    guestService.demo().then((value) => {
      if (active) setDemo(value)
    }).catch(() => {
      if (active) setError('Não foi possível carregar a demonstração. Verifique sua conexão e tente novamente.')
    })
    return () => { active = false }
  }, [retry])

  useEffect(() => {
    if (tab !== 'transcript' || focusedOrder === null) return
    const segment = segmentRefs.current[focusedOrder]
    segment?.focus()
    segment?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  }, [focusedOrder, speaker, tab, demo])

  function focusEvidence(order) {
    const segment = demo?.segments?.find((item) => item.order === order)
    setTab('transcript')
    if (segment) setSpeaker(segment.speaker || 'all')
    setFocusedOrder(order)
  }

  function evidenceLinks(evidence = []) {
    return <div className="mt-2 flex flex-wrap gap-2">{evidence.map((item, index) => (
      <button key={`${item.segment_order}-${index}`} type="button" onClick={() => focusEvidence(item.segment_order)}
        title={item.quote} className="text-sm text-primary-700 underline underline-offset-2">
        Trecho {item.segment_order + 1}{item.quote ? `: “${item.quote}”` : ''}
      </button>
    ))}</div>
  }

  const visibleSegments = demo?.segments?.filter((segment) => speaker === 'all' || segment.speaker === speaker) || []
  const sections = [
    ['topics', 'Tópicos'], ['decisions', 'Decisões'], ['action_items', 'Tarefas'], ['open_questions', 'Perguntas em aberto'],
  ]

  return <div className="mx-auto max-w-6xl space-y-6">
    <PageHeader title="Demonstração interativa" description="Explore uma reunião de exemplo com transcrição e análise sintéticas. Nenhum áudio é enviado ou processado nesta demonstração." />
    {error && <Card><CardContent><div role="alert" className="space-y-3"><p>{error}</p><Button variant="outline" onClick={() => setRetry((value) => value + 1)}>Tentar novamente</Button></div></CardContent></Card>}
    {!demo && !error && <p role="status" className="text-sm text-gray-600">Carregando demonstração...</p>}
    {demo && <>
      <Card>
        <CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle>{demo.title}</CardTitle><p className="mt-1 text-sm text-gray-600">{demo.description}</p></div><span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800">Demonstração sintética</span></div></CardHeader>
        <CardContent><p className="text-sm text-gray-600">Duração: {formatDuration(demo.duration_seconds)}</p></CardContent>
      </Card>
      <div className="flex flex-wrap gap-2" aria-label="Conteúdo da demonstração">
        <Button aria-pressed={tab === 'transcript'} variant={tab === 'transcript' ? 'primary' : 'outline'} onClick={() => setTab('transcript')}>Transcrição</Button>
        <Button aria-pressed={tab === 'summary'} variant={tab === 'summary' ? 'primary' : 'outline'} onClick={() => setTab('summary')}>Resumo e análise</Button>
      </div>
      {tab === 'transcript' ? <Card>
        <CardHeader><div className="flex flex-wrap items-center justify-between gap-3"><CardTitle>Transcrição de exemplo</CardTitle><label className="text-sm text-gray-700">Filtrar falante{' '}
          <select aria-label="Filtrar falante" value={speaker} onChange={(event) => setSpeaker(event.target.value)} className="ml-2 rounded-lg border border-gray-300 bg-white px-3 py-2">
            <option value="all">Todos</option>{demo.speakers?.map((person) => <option key={person.id} value={person.id}>{person.display_name}</option>)}
          </select>
        </label></div></CardHeader>
        <CardContent className="space-y-3">{visibleSegments.map((segment) => <article key={segment.order} id={`demo-segment-${segment.order}`} tabIndex={-1} ref={(node) => { segmentRefs.current[segment.order] = node }}
          className={`rounded-lg border p-4 ${focusedOrder === segment.order ? 'border-primary-500 bg-primary-50' : 'border-gray-200 bg-gray-50'}`}>
          <p className="mb-1 text-xs font-medium text-gray-500">{formatSeconds(segment.start)}–{formatSeconds(segment.end)} · {demo.speakers?.find((person) => person.id === segment.speaker)?.display_name || segment.speaker}</p>
          <p className="leading-7 text-gray-800">{segment.text}</p>
        </article>)}</CardContent>
      </Card> : <Card>
        <CardHeader><CardTitle>Resumo e análise</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          <section><h3 className="font-semibold text-gray-900">Resumo</h3><p className="mt-2 whitespace-pre-wrap leading-7 text-gray-700">{demo.intelligence?.summary}</p></section>
          {sections.map(([key, title]) => <section key={key} className="space-y-2"><h3 className="font-semibold text-gray-900">{title}</h3>
            {demo.intelligence?.[key]?.length ? <ul className="space-y-3">{demo.intelligence[key].map((item, index) => <li key={index} className="rounded-lg border border-gray-200 bg-gray-50 p-3">
              <p className="text-gray-800">{item.description}</p>
              {key === 'action_items' && <p className="mt-1 text-sm text-gray-600">Responsável: {item.assignee || 'Não identificado'} · Prazo: {item.due_date || 'Sem prazo explícito'}</p>}
              {evidenceLinks(item.evidence)}
            </li>)}</ul> : <p className="text-sm text-gray-500">Nenhum item identificado.</p>}
          </section>)}
        </CardContent>
      </Card>}
      <Card><CardContent className="flex flex-wrap items-center justify-between gap-4"><p className="text-sm text-gray-700">Entre para consultar os serviços disponíveis e salvar suas reuniões.</p><div className="flex gap-4 text-sm font-medium text-primary-700"><Link to={`/login?returnTo=${RETURN_TO}`}>Entrar</Link><Link to={`/signup?returnTo=${RETURN_TO}`}>Criar conta</Link></div></CardContent></Card>
    </>}
  </div>
}
