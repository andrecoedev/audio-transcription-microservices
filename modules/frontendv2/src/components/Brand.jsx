import { brand } from '../brand.js'

export default function Brand({ compact = false, className = '' }) {
  return (
    <span className={`inline-flex min-w-0 max-w-full flex-col items-start ${className}`.trim()}>
      <span className="flex min-w-0 max-w-full flex-wrap items-baseline gap-x-2">
        <span className="break-words font-semibold tracking-[0.12em] text-primary-600">{brand.company}</span>
        <span className="break-words text-xs text-gray-500" lang="ja">{brand.jp}</span>
      </span>
      {!compact && <span className="max-w-full break-words text-sm text-gray-600">{brand.product}</span>}
    </span>
  )
}
