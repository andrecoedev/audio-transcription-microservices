import { forwardRef } from 'react'
import { Menu } from 'lucide-react'
import { Link } from 'react-router-dom'
import { brand } from '../brand'

const Navbar = forwardRef(function Navbar({ onMenu, expanded, backgroundRef }, menuButtonRef) {
  return <header ref={backgroundRef} className="flex items-center justify-between border-b border-gray-200 bg-shell px-4 py-3 md:hidden">
    <Link to="/" aria-label={`${brand.company} ${brand.jp}, ${brand.product}`} className="flex items-baseline gap-2 py-1">
      <span className="text-lg font-semibold tracking-[0.12em] text-primary-700">{brand.company}</span>
      <span lang="ja" className="text-xs text-muted">{brand.jp}</span>
    </Link>
    <button ref={menuButtonRef} type="button" aria-label="Abrir navegação" aria-expanded={expanded} aria-controls="mobile-navigation" onClick={onMenu} className="rounded-lg p-2 text-ink hover:bg-gray-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"><Menu className="h-5 w-5" aria-hidden="true" /></button>
  </header>
})

export default Navbar
