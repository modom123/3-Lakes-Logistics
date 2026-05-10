import { useQuery } from '@tanstack/react-query'
import { dashboard, mockInvoices, mockAutomations } from '../api/client'
import KpiCard from '../components/KpiCard'
import StatusBadge from '../components/StatusBadge'
import Spinner from '../components/Spinner'
import {
  Users, Truck, Package, DollarSign, AlertTriangle,
  CheckCircle2, XCircle, Clock, ArrowRight, Mail, Zap
} from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const sparkData = [
  { d: 'M', v: 38 }, { d: 'T', v: 41 }, { d: 'W', v: 35 },
  { d: 'T', v: 47 }, { d: 'F', v: 52 }, { d: 'S', v: 44 },
  { d: 'S', v: 49 },
]

function AlertItem({ level, message, time }) {
  const colors = { error: 'text-red-400 bg-red-500/10', warning: 'text-yellow-400 bg-yellow-500/10', info: 'text-blue-400 bg-blue-500/10' }
  const icons  = { error: XCircle, warning: AlertTriangle, info: CheckCircle2 }
  const Icon   = icons[level] || AlertTriangle
  return (
    <div className="flex items-start gap-3 py-3 border-b border-gray-800 last:border-0">
      <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${colors[level]}`}>
        <Icon size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-200">{message}</p>
        <p className="text-xs text-gray-500 mt-0.5">{time}</p>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { data: kpis, isLoading } = useQuery({
    queryKey: ['kpis'],
    queryFn: dashboard.kpis,
    retry: false,
  })
  const { data: loads } = useQuery({
    queryKey: ['recent-loads'],
    queryFn: () => dashboard.recentLoads(6),
    retry: false,
  })

  const invoices = mockInvoices()
  const automations = mockAutomations()
  const failedAutos = automations.filter(a => a.status === 'failed').length
  const unpaidTotal = invoices.filter(i => i.status !== 'Paid').reduce((s, i) => s + i.amount, 0)

  const fmt = (n) => n === undefined || n === null ? '—' : typeof n === 'number' && n >= 1000
    ? `$${(n / 1000).toFixed(1)}K` : n

  return (
    <div className="space-y-6">
      {/* KPI Row */}
      {isLoading ? <Spinner /> : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            label="Total Carriers"
            value={kpis?.total_carriers ?? '—'}
            sub={`${kpis?.active_carriers ?? 0} active`}
            trend="up"
            icon={Users}
            color="blue"
          />
          <KpiCard
            label="MTD Loads"
            value={kpis?.mtd_loads ?? '—'}
            sub="This month"
            trend="up"
            icon={Package}
            color="green"
          />
          <KpiCard
            label="MTD Gross Revenue"
            value={fmt(kpis?.mtd_gross)}
            sub={`Avg $${kpis?.avg_rpm ?? 0}/mi`}
            trend="up"
            icon={DollarSign}
            color="purple"
          />
          <KpiCard
            label="Unpaid Invoices"
            value={kpis?.unpaid_invoices ?? invoices.filter(i=>i.status!=='Paid').length}
            sub={`$${(kpis?.unpaid_total ?? unpaidTotal).toLocaleString()} outstanding`}
            trend="down"
            icon={DollarSign}
            color="yellow"
          />
        </div>
      )}

      {/* Middle Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Revenue Trend */}
        <div className="card lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-white font-semibold">Revenue Trend</h2>
              <p className="text-gray-500 text-xs mt-0.5">Loads dispatched per day this week</p>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={sparkData} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
              <defs>
                <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2a8af6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#2a8af6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="d" tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #1f2937', borderRadius: '8px', fontSize: 12 }}
                labelStyle={{ color: '#9ca3af' }}
                itemStyle={{ color: '#60a5fa' }}
              />
              <Area type="monotone" dataKey="v" stroke="#2a8af6" strokeWidth={2} fill="url(#grad)" name="Loads" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Automation Health */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold">Automations</h2>
            <span className={failedAutos > 0 ? 'badge-red' : 'badge-green'}>
              {failedAutos > 0 ? `${failedAutos} failed` : 'All OK'}
            </span>
          </div>
          <div className="space-y-0">
            {automations.slice(0, 6).map(a => (
              <div key={a.name} className="flex items-center justify-between py-2.5 border-b border-gray-800 last:border-0">
                <div className="flex items-center gap-2 min-w-0">
                  {a.status === 'ok'      && <CheckCircle2 size={14} className="text-emerald-400 flex-shrink-0" />}
                  {a.status === 'warning' && <AlertTriangle size={14} className="text-yellow-400 flex-shrink-0" />}
                  {a.status === 'failed'  && <XCircle size={14} className="text-red-400 flex-shrink-0" />}
                  <span className="text-sm text-gray-300 truncate">{a.name}</span>
                </div>
                <span className="text-xs text-gray-500 flex-shrink-0 ml-2">{a.last_run}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Loads */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold">Recent Loads</h2>
            <a href="/dispatch" className="text-brand-400 text-xs hover:text-brand-300 flex items-center gap-1">
              View all <ArrowRight size={12} />
            </a>
          </div>
          {(loads?.items || []).length === 0 ? (
            <div className="py-8 text-center text-gray-600 text-sm">No loads yet</div>
          ) : (
            <div className="space-y-0">
              {(loads?.items || []).map(l => (
                <div key={l.id} className="flex items-center gap-3 py-3 border-b border-gray-800 last:border-0">
                  <div className="w-8 h-8 rounded-lg bg-brand-500/10 flex items-center justify-center flex-shrink-0">
                    <Package size={14} className="text-brand-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-200 truncate">
                      {l.origin_city}, {l.origin_state} → {l.dest_city}, {l.dest_state}
                    </p>
                    <p className="text-xs text-gray-500">{l.broker_name} · {l.load_number}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-sm font-medium text-white">${(l.rate_total || 0).toLocaleString()}</p>
                    <StatusBadge status={l.status} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Alerts */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold">Active Alerts</h2>
            <span className="badge-red">3 issues</span>
          </div>
          <AlertItem level="error"   message="Payout processing failed — check Stripe config" time="3 hours ago" />
          <AlertItem level="warning" message="HOS check delayed — last run 1 hour ago" time="1 hour ago" />
          <AlertItem level="warning" message="Invoice overdue 20 days — Atlas Freight $4,100" time="Today" />
          <AlertItem level="info"    message="5 emails processed via IMAP — 2 loads created" time="4 min ago" />
        </div>
      </div>
    </div>
  )
}
