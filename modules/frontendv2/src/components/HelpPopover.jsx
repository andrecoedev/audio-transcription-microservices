import { useEffect, useId, useRef, useState } from 'react'

export default function HelpPopover({ label, children }) {
  const id = useId()
  const container = useRef(null)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const [pinned, setPinned] = useState(false)
  const open = hovered || focused || pinned
  useEffect(() => {
    if (!open) return
    const close = () => { setHovered(false); setFocused(false); setPinned(false) }
    const outside = (event) => { if (!container.current?.contains(event.target)) close() }
    const escape = (event) => { if (event.key === 'Escape') close() }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) }
  }, [open])
  return <span ref={container} className="relative inline-flex align-middle" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
    <button type="button" aria-label={`Ajuda: ${label}`} aria-expanded={open} aria-describedby={open ? id : undefined}
      onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} onClick={() => setPinned(value => !value)}
      className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-gray-300 text-sm font-semibold text-gray-600 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500">?</button>
    {open && <span id={id} role="tooltip" className="absolute right-0 top-8 z-30 w-64 max-w-[calc(100vw-3rem)] rounded-lg border border-gray-200 bg-white p-3 text-left text-sm font-normal leading-relaxed text-gray-700 shadow-lg">{children}</span>}
  </span>
}
