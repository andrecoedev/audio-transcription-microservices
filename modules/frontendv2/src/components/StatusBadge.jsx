const statuses = {
  queued: ['Na fila', 'bg-gray-100 text-gray-700'],
  processing: ['Processando', 'bg-amber-50 text-amber-800'],
  completed: ['Concluída', 'bg-primary-50 text-primary-800'],
  failed: ['Falhou', 'bg-red-50 text-red-800'],
}

export default function StatusBadge({ status }) {
  const [label, colors] = statuses[status] || [status || 'Indisponível', 'bg-gray-100 text-gray-700']
  return <span className={`badge ${colors}`}>{label}</span>
}
