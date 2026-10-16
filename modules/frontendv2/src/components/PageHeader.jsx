export default function PageHeader({ title, description, children }) {
  return <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
    <div className="min-w-0"><h1 className="break-words text-[1.75rem] font-semibold leading-tight tracking-tight text-gray-900">{title}</h1>
      {description && <p className="mt-2 max-w-2xl text-sm leading-relaxed text-gray-600">{description}</p>}
    </div>
    {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
  </header>
}
