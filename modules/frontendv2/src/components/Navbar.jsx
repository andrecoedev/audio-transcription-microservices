import { Menu } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function Navbar({ onMenu, expanded }) {
  return <header className="flex items-center justify-between border-b bg-white px-5 py-4 md:hidden">
    <Link to="/" className="font-semibold tracking-[0.16em] text-primary-600">USAGI</Link>
    <button type="button" aria-label="Abrir navegação" aria-expanded={expanded} onClick={onMenu} className="rounded-lg p-2 hover:bg-gray-50"><Menu className="h-5 w-5" /></button>
  </header>
}
