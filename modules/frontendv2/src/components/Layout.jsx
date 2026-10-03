import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Navbar from './Navbar'
import Sidebar from './Sidebar'

export default function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()
  useEffect(() => { setMenuOpen(false) }, [pathname])
  useEffect(() => {
    if (!menuOpen) return
    const close = (event) => { if (event.key === 'Escape') setMenuOpen(false) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [menuOpen])
  return <div className="flex min-h-screen flex-col md:h-screen md:flex-row md:overflow-hidden">
    <a href="#main-content" className="sr-only z-50 rounded-lg bg-white p-3 focus:not-sr-only focus:absolute">Ir para o conteúdo</a>
    <Navbar expanded={menuOpen} onMenu={() => setMenuOpen(!menuOpen)} />
    <div className="hidden md:block"><Sidebar /></div>
    {menuOpen && <div className="fixed inset-0 z-40 flex md:hidden">
      <Sidebar onNavigate={() => setMenuOpen(false)} />
      <button type="button" aria-label="Fechar navegação" onClick={() => setMenuOpen(false)} className="flex-1 bg-gray-900/30" />
    </div>}
    <main id="main-content" className="min-w-0 flex-1 p-5 sm:p-8 md:overflow-y-auto lg:px-10 lg:py-10">
      <div className="mx-auto max-w-7xl"><Outlet /></div>
    </main>
  </div>
}
