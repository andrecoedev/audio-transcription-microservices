export function formatNumber(value) {
  if (value == null || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return new Intl.NumberFormat('pt-BR').format(number)
}

export function formatCount(value, singular, plural = `${singular}s`) {
  if (value == null || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  const unit = number === 1 ? singular : plural
  return `${formatNumber(number)} ${unit}`
}

export function formatDuration(seconds) {
  if (seconds == null || !Number.isFinite(Number(seconds))) return '—'
  const total = Math.max(0, Math.floor(Number(seconds)))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const remainingSeconds = total % 60
  if (hours) return `${formatCount(hours, 'hora', 'horas')} e ${formatCount(minutes, 'minuto', 'minutos')}`
  if (minutes) return `${formatCount(minutes, 'minuto', 'minutos')} e ${formatCount(remainingSeconds, 'segundo', 'segundos')}`
  return formatCount(remainingSeconds, 'segundo', 'segundos')
}

export function formatTimestamp(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit', month: 'short', year: 'numeric',
  }).format(date)
}
