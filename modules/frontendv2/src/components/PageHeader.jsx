export default function PageHeader({ title, description, children }) {
  return <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
    <div className="min-w-0"><h1 className="editorial-title text-gray-900">{title}</h1>
      {description && <p className="mt-2 max-w-2xl leading-relaxed text-gray-500">{description}</p>}
    </div>
    {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
  </header>
}
