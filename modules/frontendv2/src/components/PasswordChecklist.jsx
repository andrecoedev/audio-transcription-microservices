import { Check, Circle } from 'lucide-react'

export default function PasswordChecklist({ status, password, confirmation, id }) {
  const options = status?.passwordPolicy?.customStrengthOptions ?? {}
  const requirements = []
  if (typeof options.minPasswordLength === 'number') {
    requirements.push(['minimum', `Pelo menos ${options.minPasswordLength} caracteres`, status.meetsMinPasswordLength])
  }
  if (typeof options.maxPasswordLength === 'number') {
    requirements.push(['maximum', `No máximo ${options.maxPasswordLength.toLocaleString('pt-BR')} caracteres`, status.meetsMaxPasswordLength])
  }
  for (const [field, label] of [
    ['containsUppercaseLetter', 'Contém letra maiúscula'],
    ['containsLowercaseLetter', 'Contém letra minúscula'],
    ['containsNumericCharacter', 'Contém número'],
    ['containsNonAlphanumericCharacter', 'Contém caractere especial'],
  ]) {
    if (options[field] === true) requirements.push([field, label, status[field]])
  }
  requirements.push(['confirmation', 'As senhas coincidem', Boolean(password && confirmation && password === confirmation)])
  return <ul id={id} aria-label="Requisitos da senha" aria-live="polite" className="space-y-1 text-xs">
    {requirements.map(([key, label, met]) => {
      const satisfied = Boolean(password && met === true)
      const Icon = satisfied ? Check : Circle
      return <li key={key} className={`flex items-center gap-2 ${satisfied ? 'text-primary-700' : 'text-gray-500'}`}>
        <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
        <span className="sr-only">{satisfied ? 'Atendido: ' : 'Pendente: '}</span>{label}
      </li>
    })}
  </ul>
}
