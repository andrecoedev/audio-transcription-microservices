export function formatDuration(seconds) {
  if (seconds == null || !Number.isFinite(Number(seconds))) return '—'
  const total = Math.max(0, Math.floor(Number(seconds)))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  return hours ? `${hours}h ${minutes}min` : `${minutes}min ${total % 60}s`
}

export function formatTimestamp(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit', month: 'short', year: 'numeric',
  }).format(date)
}
