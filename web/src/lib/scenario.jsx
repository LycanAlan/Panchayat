import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { SCENARIOS, DEFAULT_PROBLEM } from '../data/scenarios.js'

/**
 * Which worked example the story pages are telling: Lakshmi's dry tank, or
 * the pothole outside 12/14. Same template, same drawings, same seven stages;
 * the household, the authority, the ladder and the record change with it.
 *
 * Set three ways, in order of precedence:
 *   ?problem=roads   on any URL, so a link can open on one story
 *   a report         from the home page, for the service the household picked
 *   the switch       in the masthead
 *
 * Remembered in this browser only. It is a reading preference, not a record:
 * nothing here reaches the runtime.
 */

const KEY = 'panchayat.problem'

const ScenarioContext = createContext(null)

function initial() {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('problem')
    if (fromUrl && SCENARIOS[fromUrl]) return fromUrl
    const saved = localStorage.getItem(KEY)
    if (saved && SCENARIOS[saved]) return saved
  } catch {
    // no URL or storage (private window, sandbox): the default story
  }
  return DEFAULT_PROBLEM
}

export function ScenarioProvider({ children }) {
  const [problem, setProblemState] = useState(initial)

  const setProblem = useCallback((next) => {
    if (!SCENARIOS[next]) return
    setProblemState(next)
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(KEY, problem)
    } catch {
      // storage unavailable: the choice lasts as long as the page does
    }
  }, [problem])

  const value = useMemo(
    () => ({ problem, scenario: SCENARIOS[problem], setProblem }),
    [problem, setProblem],
  )
  return <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>
}

/** `{ problem, scenario, setProblem }`. */
export function useScenario() {
  const ctx = useContext(ScenarioContext)
  if (!ctx) throw new Error('useScenario() outside <ScenarioProvider>')
  return ctx
}
