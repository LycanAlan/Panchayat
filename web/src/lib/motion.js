import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'

gsap.registerPlugin(ScrollTrigger)

export { gsap, ScrollTrigger }

const REDUCED = '(prefers-reduced-motion: reduce)'

export function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia(REDUCED).matches
}

export function useReducedMotion() {
  const [reduced, setReduced] = useState(prefersReducedMotion)
  useEffect(() => {
    const mq = window.matchMedia(REDUCED)
    const on = () => setReduced(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return reduced
}

/**
 * A live media query. Used to decide layout, not just decorate it:
 * the street page builds a different DOM when it cannot pin.
 */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches,
  )
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setMatches(mq.matches)
    on()
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return matches
}

/**
 * Smooth scroll, driven off the same rAF loop as ScrollTrigger so the
 * two never disagree about where the page is. Disabled outright under
 * reduced-motion — a smoothed scroll is itself motion.
 */
export function useSmoothScroll() {
  useEffect(() => {
    if (prefersReducedMotion()) return undefined

    const lenis = new Lenis({
      duration: 1.05,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      wheelMultiplier: 0.95,
      touchMultiplier: 1.4,
    })

    lenis.on('scroll', ScrollTrigger.update)
    const tick = (time) => lenis.raf(time * 1000)
    gsap.ticker.add(tick)
    gsap.ticker.lagSmoothing(0)

    return () => {
      gsap.ticker.remove(tick)
      lenis.destroy()
    }
  }, [])
}

/**
 * Scoped GSAP context. Everything a component animates is reverted on
 * unmount, which matters because route changes tear down pinned
 * triggers mid-flight.
 *
 * Under reduced motion the callback still runs but receives a context
 * whose timelines are set to their end state immediately.
 */
export function useGsap(setup, deps = []) {
  const scope = useRef(null)

  useLayoutEffect(() => {
    if (!scope.current) return undefined
    const reduced = prefersReducedMotion()
    const ctx = gsap.context((self) => setup(self, { reduced }), scope)
    ScrollTrigger.refresh()
    return () => ctx.revert()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return scope
}

/** Prepare an SVG path for a draw-in. Returns its length. */
export function primeStroke(el) {
  const len = el.getTotalLength ? el.getTotalLength() : 0
  gsap.set(el, { strokeDasharray: len, strokeDashoffset: len })
  return len
}

/** The house style for text and sheets entering: lift, never fade-only. */
export const RISE = {
  y: 22,
  opacity: 0,
  duration: 0.9,
  ease: 'power2.out',
  stagger: 0.075,
}
