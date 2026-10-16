import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Navbar from './Navbar'
import Sidebar from './Sidebar'

const focusableSelector = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'

export default function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()
  const menuButtonRef = useRef(null)
  const drawerRef = useRef(null)
  const mainRef = useRef(null)
  const navbarRef = useRef(null)
  const desktopSidebarRef = useRef(null)
  const skipLinkRef = useRef(null)

  const closeMenu = useCallback((returnFocus = true) => {
    setMenuOpen(false)
    if (returnFocus) requestAnimationFrame(() => menuButtonRef.current?.focus())
  }, [])

  useEffect(() => { closeMenu(false) }, [pathname, closeMenu])

  useEffect(() => {
    if (!window.matchMedia) return undefined
    const media = window.matchMedia('(min-width: 768px)')
    const handleBreakpoint = (event) => { if (event.matches) closeMenu(false) }
    if (media.addEventListener) media.addEventListener('change', handleBreakpoint)
    else media.addListener?.(handleBreakpoint)
    return () => {
      if (media.removeEventListener) media.removeEventListener('change', handleBreakpoint)
      else media.removeListener?.(handleBreakpoint)
    }
  }, [closeMenu])

  useEffect(() => {
    if (!menuOpen) return
    const background = [mainRef.current, navbarRef.current, desktopSidebarRef.current, skipLinkRef.current]
    const previousInert = background.map((node) => node?.inert ?? false)
    const previousOverflow = document.body.style.overflow
    background.forEach((node) => { if (node) node.inert = true })
    document.body.style.overflow = 'hidden'
    const focusables = () => Array.from(drawerRef.current?.querySelectorAll(focusableSelector) || [])
    requestAnimationFrame(() => focusables()[0]?.focus())
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeMenu()
        return
      }
      if (event.key !== 'Tab') return
      const items = focusables()
      if (!items.length) { event.preventDefault(); drawerRef.current?.focus(); return }
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && (document.activeElement === first || !drawerRef.current?.contains(document.activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !drawerRef.current?.contains(document.activeElement))) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      background.forEach((node, index) => { if (node) node.inert = previousInert[index] })
      document.body.style.overflow = previousOverflow
    }
  }, [menuOpen, closeMenu])

  return <div className="flex min-h-screen flex-col bg-canvas md:h-screen md:flex-row md:overflow-hidden">
    <a ref={skipLinkRef} href="#main-content" className="sr-only z-50 rounded-lg bg-white p-3 focus:not-sr-only focus:absolute">Ir para o conteúdo</a>
    <div ref={desktopSidebarRef} className="hidden md:block"><Sidebar /></div>
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <Navbar ref={menuButtonRef} backgroundRef={navbarRef} expanded={menuOpen} onMenu={() => setMenuOpen(true)} />
      <main ref={mainRef} id="main-content" className="min-w-0 flex-1 p-5 sm:p-8 md:overflow-y-auto lg:px-10 lg:py-10">
        <div className="mx-auto max-w-7xl"><Outlet /></div>
      </main>
    </div>
    {menuOpen && <div className="fixed inset-0 z-40 flex md:hidden">
      <div id="mobile-navigation" ref={drawerRef} role="dialog" aria-modal="true" aria-label="Navegação principal" tabIndex={-1} className="relative z-10 h-full shadow-xl">
        <Sidebar compact onNavigate={() => closeMenu(false)} />
      </div>
      <button type="button" aria-label="Fechar navegação" onClick={() => closeMenu()} className="flex-1 bg-ink/40" />
    </div>}
  </div>
}
