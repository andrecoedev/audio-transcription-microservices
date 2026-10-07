import { useEffect, useRef, useState } from 'react'
import Button from './Button'
import { audioService } from '../services/audioService'
import { formatSeconds } from '../utils/format'

function EvidenceLinks({ evidence = [], references = [] }) {
  return <div className="mt-1 text-sm text-gray-500">{evidence.map((item, index) => {
    const reference = references.find(ref => ref.segment_order === item.segment_order)
    return <a key={index} href={`#segment-${item.segment_order}`} title={item.quote} className="mr-3 text-primary-700 underline">
      {reference ? `${formatSeconds(reference.start)}–${formatSeconds(reference.end)}` : `Trecho ${item.segment_order + 1}`}
    </a>
  })}</div>
}

export default function MeetingIntelligencePanel({ meetingId, onResultChange, initialTab = 'all' }) {
  const [status, setStatus] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const notifiedRevision = useRef(null)

  useEffect(() => {
    let cancelled = false
    let timer
    async function poll() {
      try {
        const current = await audioService.getMeetingIntelligenceStatus(meetingId)
        const content = current.completed_revision ? await audioService.getMeetingIntelligenceResult(meetingId) : null
        if (cancelled) return
        setStatus(current)
        setResult(content)
        if (content?.revision !== notifiedRevision.current) {
          notifiedRevision.current = content?.revision ?? null
          onResultChange?.(content?.revision ?? null)
        }
        setError('')
        if (['pending', 'processing'].includes(current.generation?.status)) timer = setTimeout(poll, 3000)
      } catch {
        if (!cancelled) setError('Não foi possível consultar a análise da reunião.')
      }
    }
    poll()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [meetingId, refresh, onResultChange])

  async function generate() {
    setSubmitting(true)
    setError('')
    try {
      await audioService.requestMeetingIntelligence(meetingId, Boolean(result))
      setRefresh(value => value + 1)
    } catch (failure) {
      setError(failure.message || 'Não foi possível gerar o resumo. Tente novamente.')
    } finally { setSubmitting(false) }
  }

  const state = status?.generation?.status
  const busy = ['pending', 'processing'].includes(state)
  const content = result?.content
  const visibleSections = initialTab === 'all' ? ['summary', 'topics', 'decisions', 'actions', 'questions'] : [initialTab]
  const sections = [
    ['topics', 'Tópicos', content?.topics], ['decisions', 'Decisões', content?.decisions],
    ['actions', 'Tarefas', content?.action_items], ['questions', 'Perguntas em aberto', content?.open_questions],
  ]

  return <section className="space-y-4">
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {error && <Button variant="outline" onClick={() => setRefresh(value => value + 1)}>Consultar novamente</Button>}
    {!status && !error && <p role="status" className="text-sm text-gray-500">Consultando análise...</p>}
    {status && !status.generation && !result && <p className="text-sm text-gray-600">Ainda não há análise desta reunião.</p>}
    {status && !status.configured && <p className="text-sm text-gray-600">A análise com IA está indisponível no momento.</p>}
    {busy && <p role="status" className="text-sm text-gray-600">{result ? 'Gerando novamente; a versão anterior continua disponível.' : 'Gerando resumo...'}</p>}
    {state === 'failed' && <p role="alert" className="text-sm text-red-700">A geração falhou. Você pode tentar novamente.</p>}
    {status && <Button onClick={generate} disabled={submitting || busy || !status.configured}>
      {submitting ? 'Solicitando...' : result ? 'Gerar novamente' : state === 'failed' ? 'Tentar novamente' : 'Gerar resumo'}
    </Button>}
    {content && <div className="space-y-5">
      <p className="text-xs text-gray-500">Versão {result.revision} · {result.provider} · {result.model}</p>
      {visibleSections.includes('summary') && <section><h3 className="font-semibold text-gray-900">Resumo</h3><p className="mt-2 whitespace-pre-wrap leading-7">{content.summary}</p></section>}
      {sections.filter(([key]) => visibleSections.includes(key)).map(([key, heading, items]) => <section key={key} className="space-y-2">
        <h3 className="font-semibold text-gray-900">{heading}</h3>
        {items?.length ? <ul className="space-y-3">{items.map((item, index) => <li key={index} className="rounded-lg border border-gray-200 bg-gray-50 p-3">
          <p>{item.description}</p>
          {key === 'actions' && <p className="mt-1 text-sm text-gray-600">Responsável: {item.assignee || 'Não identificado'} · Prazo: {item.due_date || 'Sem prazo explícito'}</p>}
          <EvidenceLinks evidence={item.evidence} references={result.references} />
        </li>)}</ul> : <p className="text-sm text-gray-500">Nenhum item identificado.</p>}
      </section>)}
    </div>}
  </section>
}
