import { useEffect } from 'react'
import { Routes, Route, useLocation, Navigate } from 'react-router-dom'
import Masthead from './components/Masthead.jsx'
import Footer from './components/Footer.jsx'
import Index from './routes/Index.jsx'
import Case from './routes/Case.jsx'
import Street from './routes/Street.jsx'
import Process from './routes/Process.jsx'
import About from './routes/About.jsx'
import Live from './routes/Live.jsx'
import { useSmoothScroll, ScrollTrigger } from './lib/motion.js'
import { useScenario } from './lib/scenario.jsx'

const TITLES = {
  '/': 'Panchayat — a complaint closed is not a problem fixed',
  '/street': 'The street · Ward 12 layout — Panchayat',
  '/process': 'The process · seven stages — Panchayat',
  '/about': 'Boundaries — Panchayat',
  '/live': 'Your reports · live — Panchayat',
}

function Page() {
  const { pathname } = useLocation()
  const { scenario } = useScenario()

  useEffect(() => {
    document.title =
      pathname === '/case'
        ? `The case · ${scenario.CASE.id} — Panchayat`
        : TITLES[pathname] ?? (pathname.startsWith('/live/') ? 'The live file — Panchayat' : 'Panchayat')
  }, [pathname, scenario])

  // Switching the story swaps text of different lengths under pinned
  // sections, so their triggers must measure again.
  useEffect(() => {
    const id = requestAnimationFrame(() => ScrollTrigger.refresh())
    return () => cancelAnimationFrame(id)
  }, [scenario])

  useEffect(() => {
    window.scrollTo(0, 0)
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
      <Route path="/live" element={<Live />} />
      <Route path="/live/:caseId" element={<Live />} />
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
