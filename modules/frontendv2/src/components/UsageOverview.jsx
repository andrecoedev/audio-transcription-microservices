import { useEffect, useState } from 'react'

import Button from './Button'
import HelpPopover from './HelpPopover'
import { usageService } from '../services/usageService'
import { useAuthStore } from '../stores/authStore'
import { formatCount, formatNumber, formatTimestamp } from '../utils/format'

function numberValue(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 ? number : null
}

function aggregate(metrics, metricName, unit) {
  const matching = metrics.filter((metric) => metric.metric === metricName && metric.unit === unit)
  const observations = matching.reduce((total, metric) => total + (numberValue(metric.observations) ?? 0), 0)
  const knownValues = matching.map((metric) => numberValue(metric.quantity_total)).filter((value) => value !== null)
  const unknownCount = matching.reduce((total, metric) => {
    const explicitUnknown = numberValue(metric.unknown_observations) ?? 0
    const observationsForMetric = numberValue(metric.observations) ?? 0
    return total + Math.max(explicitUnknown, metric.quantity_total == null ? observationsForMetric : 0)
  }, 0)

  return {
    observations,
    total: knownValues.length ? knownValues.reduce((sum, value) => sum + value, 0) : null,
    partial: knownValues.length > 0 && unknownCount > 0,
  }
}

function MetricValue({ metric, emptyLabel, format }) {
  if (!metric.observations) return <span>{emptyLabel}</span>
  if (metric.total === null) return <span>Não informado</span>
  return <>
    <span>{format(metric.total)}</span>
    {metric.partial && <span className="mt-1 block text-xs font-normal text-amber-800">Soma parcial: há registros sem quantidade informada.</span>}
  </>
}

export default function UsageOverview() {
  const userId = useAuthStore((state) => state.user?.id)
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const [request, setRequest] = useState({ userId: null, overview: null, loading: true, error: false })
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    if (!isAuthenticated || !userId) return undefined

    let active = true
    setRequest({ userId, overview: null, loading: true, error: false })
    usageService.getOverview().then((result) => {
      if (active) setRequest({ userId, overview: result, loading: false, error: false })
    }).catch(() => {
      if (active) setRequest({ userId, overview: null, loading: false, error: true })
    })

    return () => { active = false }
  }, [isAuthenticated, userId, retry])

  if (!isAuthenticated || !userId) return null

  const currentRequest = request.userId === userId ? request : null
  const loading = !currentRequest || currentRequest.loading
  const error = Boolean(currentRequest?.error)
  const overview = currentRequest?.overview
  const metrics = Array.isArray(overview?.metrics) ? overview.metrics : []
  const hasRecordedData = metrics.some((metric) => (numberValue(metric.observations) ?? 0) > 0)
  const audio = aggregate(metrics, 'audio_seconds', 'second')
  const attempts = aggregate(metrics, 'attempt', 'attempt')
  const after = overview?.after ? formatTimestamp(overview.after) : null
  const before = overview?.before ? formatTimestamp(overview.before) : null
  const validAfter = after && after !== '—' ? after : null
  const validBefore = before && before !== '—' ? before : null
  const period = validAfter && validBefore ? `Período: ${validAfter} – ${validBefore}`
    : validAfter ? `A partir de ${validAfter}`
      : validBefore ? `Até ${validBefore}` : null

  return <section aria-labelledby="usage-overview-title" className="space-y-3">
    <div className="flex items-center gap-2">
      <h3 id="usage-overview-title" className="font-semibold text-gray-900">Consumo registrado</h3>
      <HelpPopover label="Consumo registrado">
        A duração é uma medida técnica do áudio nas tentativas, inclusive as que falharam. Ela não representa faturamento nem saldo de créditos.
      </HelpPopover>
    </div>

    {loading && <p role="status" className="text-sm text-gray-600">Carregando dados de uso…</p>}
    {error && <div role="alert" className="space-y-2 text-sm text-amber-900">
      <p>Não foi possível carregar os dados de uso.</p>
      <Button type="button" variant="outline" size="sm" onClick={() => setRetry((value) => value + 1)}>Tentar novamente</Button>
    </div>}
    {!loading && !error && period && <p className="text-xs text-gray-500">{period}</p>}
    {!loading && !error && !hasRecordedData && <p className="text-sm text-gray-600">Nenhum dado de uso registrado.</p>}
    {!loading && !error && hasRecordedData && <dl className="grid gap-3 text-sm sm:grid-cols-2">
      <div className="rounded-lg bg-gray-50 p-3">
        <dt className="text-gray-600">Áudio registrado</dt>
        <dd className="mt-1 font-medium text-gray-900">
          <MetricValue metric={audio} emptyLabel="Sem registros" format={(seconds) => `${formatNumber(seconds / 60, { maximumFractionDigits: 2 })} min`} />
        </dd>
      </div>
      <div className="rounded-lg bg-gray-50 p-3">
        <dt className="text-gray-600">Operações iniciadas</dt>
        <dd className="mt-1 font-medium text-gray-900">
          <MetricValue metric={attempts} emptyLabel="Sem registros" format={(count) => formatCount(count, 'operação iniciada', 'operações iniciadas')} />
        </dd>
      </div>
    </dl>}

    <p className="text-xs text-gray-600">Contratação de planos ainda não disponível.</p>
  </section>
}
