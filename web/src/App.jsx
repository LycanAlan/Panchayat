import { useEffect } from 'react'
import { Routes, Route, useLocation, Navigate } from 'react-router-dom'
import Masthead from './components/Masthead.jsx'
import Footer from './components/Footer.jsx'
import Index from './routes/Index.jsx'
import Case from './routes/Case.jsx'
import Street from './routes/Street.jsx'
import Process from './routes/Process.jsx'
import About from './routes/About.jsx'
import { useSmoothScroll, ScrollTrigger } from './lib/motion.js'

const TITLES = {
  '/': 'Panchayat — a complaint closed is not a problem fixed',
  '/case': 'The case · PNC-2026-0912 — Panchayat',
  '/street': 'The street · Ward 12 layout — Panchayat',
  '/process': 'The process · seven stages — Panchayat',
  '/about': 'Boundaries — Panchayat',
}

function Page() {
  const { pathname } = useLocation()

  useEffect(() => {
    window.scrollTo(0, 0)
    document.title = TITLES[pathname] ?? 'Panchayat'
    // A route swap replaces every pinned section on the page; without
    // this the old triggers keep their stale measurements.
    const id = requestAnimationFrame(() => ScrollTrigger.refresh())
    return () => cancelAnimationFrame(id)
  }, [pathname])

  return (
    <Routes>
      <Route path="/" element={<Index />} />
      <Route path="/case" element={<Case />} />
      <Route path="/street" element={<Street />} />
      <Route path="/process" element={<Process />} />
      <Route path="/about" element={<About />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  useSmoothScroll()

  return (
    <>
      <a href="#record" className="sr-only">
        Skip to the record
      </a>
      <Masthead />
      <main id="record">
        <Page />
      </main>
      <Footer />
    </>
  )
}
