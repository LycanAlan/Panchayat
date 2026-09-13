/**
 * The only file on the site that touches the network.
 *
 * Everything else renders a fixture from src/data. The live pages come
 * through here, to POST /api, which is the same origin in production (one
 * Lambda serves the site and the API) and a vite proxy in development — so
 * there is no base URL to configure and no CORS to get wrong.
 */

const IDENTITY_KEY = 'panchayat.identity'

/**
 * This browser, as a household. There is no login yet — the runtime takes
 * whatever ids it is given — so the ids are synthetic, minted once, and kept
 * in this browser only. Clearing site data makes you a new household.
 */
export function identity() {
  try {
    const saved = JSON.parse(localStorage.getItem(IDENTITY_KEY))
    if (saved?.household_id && saved?.member_id) return saved
  } catch {
    // unavailable or corrupt storage: mint a fresh identity below
  }
  const token = () => crypto.randomUUID().replace(/-/g, '').slice(0, 12)
  const minted = { household_id: `hh_web_${token()}`, member_id: `mem_web_${token()}` }
  try {
    localStorage.setItem(IDENTITY_KEY, JSON.stringify(minted))
  } catch {
    // private window: the identity lasts as long as the page does
  }
  return minted
}

async function call(body) {
  const res = await fetch('/api', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  let data = null
  try {
    data = await res.json()
  } catch {
    // a non-JSON answer is reported by status below
  }
  if (!res.ok || !data || data.error) {
    const err = new Error(data?.error ?? `HTTP ${res.status}`)
    err.data = data
    throw err
  }
  return data
}

/** One household reports one problem. Resolves to the runtime's `result`. */
export async function report({ text, segment }) {
  const data = await call({ action: 'report', ...identity(), text, segment, service: 'water' })
  return data.result
}

export function getCase(caseId) {
  return call({ action: 'get_case', case_id: caseId, household_id: identity().household_id })
}

export function listCases() {
  return call({ action: 'list_cases', household_id: identity().household_id })
}

/** A named person approves one drafted filing. Rule 4's other half. */
export function approve(idempotencyKey) {
  return call({ action: 'approve', idempotency_key: idempotencyKey, member_id: identity().member_id })
}
