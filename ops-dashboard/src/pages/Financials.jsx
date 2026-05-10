import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboard, mockInvoices, mockRevenue } from '../api/client'
import KpiCard from '../components/KpiCard'
import Spinner from '../components/Spinner'
import Empty from '../components/Empty'
import {
  DollarSign, TrendingUp, FileText, AlertCircle,
  CheckCircle2, Clock, Search, ArrowUpRight
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Legend, LineChart, Line, CartesianGrid
} from 'recharts'

function InvoiceStatusBadge({ status }) {
  const s = (status || '').toLowerCase()
  if (s === 'paid')    return <span className="badge-green">Paid</span>
  if (s === 'overdue') return <span className="badge-red">Overdue</span>
  return <span className="badge-yellow">Unpaid</span>
}

export default function Financials() {
  const [search, setSearch] = useState('')
  const [invFilter, setInvFilter] = useState('')
  const [activeTab, setActiveTab] = useState('overview')

  const { data: kpis, isLoading } = useQuery({
    queryKey: ['kpis'],
    queryFn: dashboard.kpis,
    retry: false,
  })

  const invoices = mockInvoices()
  const revenue  = mockRevenue()

  const filtered = invoices.filter(inv => {
    if (invFilter && inv.status.toLowerCase() !== invFilter.toLowerCase()) return false
    if (search && ![inv.carrier_name, inv.load_number].some(v => v?.toLowerCase().includes(search.toLowerCase()))) return false
    return true
  })

  const totalRevenue  = revenue.reduce((s, r) => s + r.revenue, 0)
  const totalFees     = revenue.reduce((s, r) => s + r.fees, 0)
  const paidInvoices  = invoices.filter(i => i.status === 'Paid')
  const unpaidInvoices= invoices.filter(i => i.status !== 'Paid')
  const overdueTotal  = invoices.filter(i => i.status === 'Overdue').reduce((s,i) => s + i.amount, 0)

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null
    return (
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 text-xs">
        <p className="text-gray-400 mb-1">{label}</p>
        {payload.map(p => (
          <p key={p.name} style={{ color: p.color }}>${p.value.toLocaleString()}</p>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* KPIs */}
      {isLoading ? <Spinner /> : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            label="MTD Gross Revenue"
            value={kpis?.mtd_gross ? `$${Number(kpis.mtd_gross).toLocaleString()}` : '$48,200'}
            sub="This month so far"
            trend="up"
            icon={DollarSign}
            color="green"
          />
          <KpiCard
            label="Dispatcher Fees (MTD)"
            value={kpis?.mtd_dispatch_fees ? `$${Number(kpis.mtd_dispatch_fees).toLocaleString()}` : '$4,820'}
            sub="10% full-service"
            trend="up"
            icon={TrendingUp}
            color="blue"
          />
          <KpiCard
            label="Unpaid Invoices"
            value={unpaidInvoices.length}
            sub={`$${unpaidInvoices.reduce((s,i) => s+i.amount,0).toLocaleString()} outstanding`}
            trend="down"
            icon={FileText}
            color="yellow"
          />
          <KpiCard
            label="Overdue Amount"
            value={`$${overdueTotal.toLocaleString()}`}
            sub="Needs immediate attention"
            trend="down"
            icon={AlertCircle}
            color="red"
          />
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-gray-800">
        {['overview', 'invoices'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors capitalize ${
              activeTab === tab
                ? 'text-white border-brand-500'
                : 'text-gray-500 border-transparent hover:text-gray-300'
            }`}
          >
            {tab === 'overview' ? 'Revenue Overview' : 'Invoice Management'}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Charts row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card">
              <h3 className="text-white font-semibold mb-1">Revenue vs Dispatcher Fees</h3>
              <p className="text-gray-500 text-xs mb-4">Last 7 months</p>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={revenue} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
                  <XAxis dataKey="month" tick={{ fill:'#6b7280', fontSize:11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill:'#6b7280', fontSize:11 }} axisLine={false} tickLine={false}
                    tickFormatter={v => `$${(v/1000).toFixed(0)}K`} />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />
                  <Bar dataKey="revenue" name="Revenue" fill="#2a8af6" radius={[3,3,0,0]} />
                  <Bar dataKey="fees"    name="Fees"    fill="#10b981" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <h3 className="text-white font-semibold mb-1">Revenue Trend</h3>
              <p className="text-gray-500 text-xs mb-4">Monthly gross revenue</p>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={revenue} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="month" tick={{ fill:'#6b7280', fontSize:11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill:'#6b7280', fontSize:11 }} axisLine={false} tickLine={false}
                    tickFormatter={v => `$${(v/1000).toFixed(0)}K`} />
                  <Tooltip content={<CustomTooltip />} />
                  <Line type="monotone" dataKey="revenue" name="Revenue" stroke="#2a8af6" strokeWidth={2} dot={{ fill:'#2a8af6', r:3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Summary stats */}
          <div className="grid grid-cols-3 gap-4">
            <div className="card text-center">
              <p className="text-3xl font-bold text-white">${(totalRevenue/1000).toFixed(0)}K</p>
              <p className="text-gray-500 text-sm mt-1">7-Month Revenue</p>
            </div>
            <div className="card text-center">
              <p className="text-3xl font-bold text-emerald-400">${(totalFees/1000).toFixed(1)}K</p>
              <p className="text-gray-500 text-sm mt-1">7-Month Fees Earned</p>
            </div>
            <div className="card text-center">
              <p className="text-3xl font-bold text-brand-400">
                {totalRevenue > 0 ? ((totalFees/totalRevenue)*100).toFixed(1) : 0}%
              </p>
              <p className="text-gray-500 text-sm mt-1">Avg Margin</p>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'invoices' && (
        <div className="space-y-4">
          {/* Invoice filters */}
          <div className="card p-4 flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 min-w-48">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                className="input w-full pl-9"
                placeholder="Search carrier or load number…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
            <select className="input" value={invFilter} onChange={e => setInvFilter(e.target.value)}>
              <option value="">All</option>
              <option value="Paid">Paid</option>
              <option value="Unpaid">Unpaid</option>
              <option value="Overdue">Overdue</option>
            </select>
            <div className="flex items-center gap-3 text-sm">
              <span className="text-emerald-400">{paidInvoices.length} paid</span>
              <span className="text-yellow-400">{unpaidInvoices.filter(i=>i.status==='Unpaid').length} unpaid</span>
              <span className="text-red-400">{invoices.filter(i=>i.status==='Overdue').length} overdue</span>
            </div>
          </div>

          <div className="card overflow-hidden p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800">
                    {['Carrier', 'Load #', 'Amount', 'Due Date', 'Days Overdue', 'Status', 'Action'].map(h => (
                      <th key={h} className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(inv => (
                    <tr key={inv.id} className="table-row">
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-7 h-7 rounded-lg bg-gray-800 flex items-center justify-center text-xs font-bold text-gray-400">
                            {(inv.carrier_name||'U')[0]}
                          </div>
                          <span className="text-gray-200 font-medium">{inv.carrier_name}</span>
                        </div>
                      </td>
                      <td className="px-5 py-4 font-mono text-gray-400 text-xs">{inv.load_number}</td>
                      <td className="px-5 py-4 text-white font-semibold">${inv.amount.toLocaleString()}</td>
                      <td className="px-5 py-4 text-gray-400">{inv.due_date}</td>
                      <td className="px-5 py-4">
                        {inv.days_overdue > 0
                          ? <span className="text-red-400 font-medium">{inv.days_overdue}d</span>
                          : <span className="text-gray-500">—</span>
                        }
                      </td>
                      <td className="px-5 py-4"><InvoiceStatusBadge status={inv.status} /></td>
                      <td className="px-5 py-4">
                        {inv.status !== 'Paid' && (
                          <button className="btn-ghost text-xs px-3 py-1.5">Send Reminder</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
