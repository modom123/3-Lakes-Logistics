const BASE = import.meta.env.VITE_API_URL || '/api'
const TOKEN = import.meta.env.VITE_API_TOKEN || 'change-me-in-prod'

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    },
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

// ── Carriers ─────────────────────────────────────────────────────────────────
export const carriers = {
  list: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request(`/carriers/?${q}`)
  },
  get: (id) => request(`/carriers/${id}`),
  setStatus: (id, status) =>
    request(`/carriers/${id}/status?new_status=${status}`, { method: 'PATCH' }),
}

// ── Fleet ─────────────────────────────────────────────────────────────────────
export const fleet = {
  list: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request(`/fleet/?${q}`)
  },
  get: (id) => request(`/fleet/${id}`),
  setStatus: (id, status) =>
    request(`/fleet/${id}/status?new_status=${status}`, { method: 'PATCH' }),
}

// ── Dashboard KPIs ────────────────────────────────────────────────────────────
export const dashboard = {
  kpis: () => request('/dashboard/kpis'),
  recentLoads: (limit = 10) => request(`/dashboard/recent-loads?limit=${limit}`),
}

// ── Email log ────────────────────────────────────────────────────────────────
export const email = {
  log: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request(`/email-log?${q}`)
  },
  sources: () => request('/email/sources'),
  stats: () => request('/email/stats'),
  pollImap: () => request('/email/imap/poll', { method: 'POST' }),
}

// ── Prospecting / Leads ───────────────────────────────────────────────────────
export const leads = {
  list: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request(`/leads/?${q}`)
  },
}

// ── Compliance ────────────────────────────────────────────────────────────────
export const compliance = {
  list: () => request('/compliance/'),
  carrier: (id) => request(`/compliance/${id}`),
}

// ── Executives ────────────────────────────────────────────────────────────────
export const executives = {
  dashboard: () => request('/executives/dashboard'),
  list: () => request('/executives'),
}

// ── Mock helpers for data not yet in backend ─────────────────────────────────
export function mockInvoices() {
  return [
    { id: '1', carrier_name: 'Sunshine Freight', amount: 2500, status: 'Unpaid', due_date: '2026-05-05', load_number: 'L-1001', days_overdue: 5 },
    { id: '2', carrier_name: 'Big Rig Express',  amount: 1850, status: 'Paid',   due_date: '2026-05-01', load_number: 'L-1002', days_overdue: 0 },
    { id: '3', carrier_name: 'Swift Carriers',   amount: 3200, status: 'Unpaid', due_date: '2026-04-28', load_number: 'L-1003', days_overdue: 12 },
    { id: '4', carrier_name: 'Eagle Transport',  amount: 1600, status: 'Paid',   due_date: '2026-05-08', load_number: 'L-1004', days_overdue: 0 },
    { id: '5', carrier_name: 'Atlas Freight',    amount: 4100, status: 'Overdue',due_date: '2026-04-20', load_number: 'L-1005', days_overdue: 20 },
    { id: '6', carrier_name: 'Prime Logistics',  amount: 2200, status: 'Paid',   due_date: '2026-05-09', load_number: 'L-1006', days_overdue: 0 },
    { id: '7', carrier_name: 'Horizon Trucking', amount: 1950, status: 'Unpaid', due_date: '2026-05-03', load_number: 'L-1007', days_overdue: 7 },
  ]
}

export function mockRevenue() {
  return [
    { month: 'Nov', revenue: 38200, fees: 3820 },
    { month: 'Dec', revenue: 41500, fees: 4150 },
    { month: 'Jan', revenue: 35800, fees: 3580 },
    { month: 'Feb', revenue: 44100, fees: 4410 },
    { month: 'Mar', revenue: 52300, fees: 5230 },
    { month: 'Apr', revenue: 49800, fees: 4980 },
    { month: 'May', revenue: 48200, fees: 4820 },
  ]
}

export function mockAutomations() {
  return [
    { name: 'ELD Sync — Motive',       status: 'ok',      last_run: '2 min ago',  carriers: 18 },
    { name: 'ELD Sync — Samsara',      status: 'ok',      last_run: '3 min ago',  carriers: 12 },
    { name: 'GPS Tracking',            status: 'ok',      last_run: '30 sec ago', carriers: 42 },
    { name: 'HOS Compliance Check',    status: 'warning', last_run: '1 hr ago',   carriers: 42 },
    { name: 'FMCSA Safety Monitor',    status: 'ok',      last_run: '6 hr ago',   carriers: 42 },
    { name: 'Email Ingest (SendGrid)', status: 'ok',      last_run: '5 min ago',  carriers: null },
    { name: 'Email Ingest (IMAP)',     status: 'ok',      last_run: '4 min ago',  carriers: null },
    { name: 'Invoice Auto-send',       status: 'ok',      last_run: '1 hr ago',   carriers: null },
    { name: 'Compliance Sweep',        status: 'ok',      last_run: '6 hr ago',   carriers: 42 },
    { name: 'Payout Processing',       status: 'failed',  last_run: '3 hr ago',   carriers: null },
  ]
}
