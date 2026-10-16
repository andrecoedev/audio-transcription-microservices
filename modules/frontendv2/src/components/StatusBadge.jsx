const statuses = {
  queued: ['Na fila', 'bg-gray-100 text-gray-700'],
  processing: ['Processando', 'bg-[var(--usagi-warning-soft)] text-warning'],
  completed: ['Concluída', 'bg-[var(--usagi-success-soft)] text-success'],
  failed: ['Falhou', 'bg-[var(--usagi-danger-soft)] text-danger'],
}

export default function StatusBadge({ status }) {
  const [label, colors] = statuses[status] || ['Status indisponível', 'bg-gray-100 text-gray-700']
  return <span className={`badge ${colors}`}>{label}</span>
}
