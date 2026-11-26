import { forwardRef } from 'react'
import { Link } from 'react-router-dom'
import Brand from './Brand'

const Navbar = forwardRef(function Navbar({ onMenu, expanded, backgroundRef }, menuButtonRef) {
  return <header ref={backgroundRef} className="sticky top-0 z-20 flex items-center justify-between border-b border-gray-200 bg-canvas px-4 py-2 min-[861px]:hidden">
    <Link to="/" className="py-1 text-lg">
      <Brand />
    </Link>
    <button ref={menuButtonRef} type="button" aria-label="Abrir navegação" aria-expanded={expanded} aria-controls="mobile-navigation" onClick={onMenu} className="btn-secondary px-4 text-xs">Menu</button>
  </header>
})

export default Navbar
