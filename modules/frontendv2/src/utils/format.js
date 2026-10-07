export function formatNumber(value, options = {}) {
  if (value == null || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return new Intl.NumberFormat('pt-BR', options).format(number)
}

export function formatCount(value, singular, plural) {
  if (value == null || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  const unit = number === 1 ? singular : plural
  return `${formatNumber(number)} ${unit}`
}

export function formatSeconds(value, fractionDigits = 1) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return `${formatNumber(value, { minimumFractionDigits: fractionDigits, maximumFractionDigits: fractionDigits })} s`
}

export function getDisplayFilename(transcription) {
  const originalFilename = transcription?.original_filename?.trim()
  if (originalFilename) return originalFilename

  const filename = transcription?.filename?.trim()
  if (!filename) return 'Arquivo de áudio'

  const storageKeyPattern = /^(?:[\da-f]{32}|[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12})(?:\.[\da-z]{1,10})?$/i
  return storageKeyPattern.test(filename) ? 'Arquivo de áudio' : filename
}

export function formatDuration(seconds) {
  if (seconds == null || !Number.isFinite(Number(seconds))) return '—'
  const total = Math.max(0, Math.floor(Number(seconds)))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const remainingSeconds = total % 60
  if (hours && minutes) return `${formatCount(hours, 'hora', 'horas')} e ${formatCount(minutes, 'minuto', 'minutos')}`
  if (hours) return formatCount(hours, 'hora', 'horas')
  if (minutes && remainingSeconds) return `${formatCount(minutes, 'minuto', 'minutos')} e ${formatCount(remainingSeconds, 'segundo', 'segundos')}`
  if (minutes) return formatCount(minutes, 'minuto', 'minutos')
  return formatCount(remainingSeconds, 'segundo', 'segundos')
}

export function formatTimestamp(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit', month: 'short', year: 'numeric',
  }).format(date)
}
