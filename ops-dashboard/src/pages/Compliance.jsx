import { useQuery } from '@tanstack/react-query'
import { carriers, mockAutomations } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import Spinner from '../components/Spinner'
import { useState } from 'react'
import {
  ShieldCheck, AlertTriangle, CheckCircle2, XCircle,
  Clock, Zap, RefreshCw, Search
} from 'lucide-react'

function AutomationRow({ name, status, last_run, carriers: count }) {
  const icon = status === 'ok'
    ? <CheckCircle2 size={16} className="text-emerald-400" />
    : status === 'warning'
    ? <AlertTriangle size={16} className="text-yellow-400" />
    : <XCircle size={16} className="text-red-400" />

  const badge = status === 'ok'
    ? 'badge-green'
    : status === 'warning'
    ? 'badge-yellow'
    : 'badge-red'

  return (
    <div className="flex items-center gap-4 py-3.5 border-b border-gray-800 last:border-0">
      <div className="flex-shrink-0">{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-gray-200 text-sm font-medium">{name}</p>
        {count !== null && <p className="text-gray-500 text-xs mt-0.5">{count} carriers affected</p>}
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">
        <span className={badge}>{status}</span>
        <span className="text-gray-600 text-xs w-24 text-right">{last_run}</span>
      </div>
    </div>
  )
}

function ComplianceRow({ carrier }) {
  const insuranceOk = carrier.status === 'active'
  const complianceLight = insuranceOk ? 'green' : 'yellow'
  return (
    <tr className="table-row">
      <td className="px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-gray-800 flex items-center justify-center text-xs font-bold text-gray-400">
            {(carrier.company_name||'U')[0]}
          </div>
          <div>
            <p className="text-gray-200 font-medium">{carrier.company_name}</p>
            <p className="text-gray-500 text-xs">DOT {carrier.dot_number || '—'}</p>
          </div>
        </div>
      </td>
      <td className="px-5 py-4">
        <StatusBadge status={carrier.status} />
      </td>
      <td className="px-5 py-4">
        {insuranceOk
          ? <span className="badge-green">Current</span>
          : <span className="badge-yellow">Pending</span>
        }
      </td>
      <td className="px-5 py-4">
        <span className={complianceLight === 'green' ? 'badge-green' : 'badge-yellow'}>
          {complianceLight === 'green' ? 'OK' : 'Review'}
        </span>
      </td>
      <td className="px-5 py-4">
        {carrier.status === 'active'
          ? <span className="badge-green">Syncing</span>
          : <span className="badge-gray">Inactive</span>
        }
      </td>
      <td className="px-5 py-4">
        {carrier.status === 'active'
          ? <span className="badge-green">Compliant</span>
          : <span className="badge-yellow">Unknown</span>
        }
      </td>
    </tr>
  )
}

export default function Compliance() {
  const [search, setSearch] = useState('')
  const automations = mockAutomations()
  const failedCount = automations.filter(a => a.status === 'failed').length
  const warningCount = automations.filter(a => a.status === 'warning').length
  const okCount = automations.filter(a => a.status === 'ok').length

  const { data, isLoading } = useQuery({
    queryKey: ['carriers'],
    queryFn: () => carriers.list(),
    retry: false,
  })

  const items = (data?.items || []).filter(c =>
    !search || [c.company_name, c.dot_number].some(v => v?.toLowerCase().includes(search.toLowerCase()))
  )

  return (
    <div className="space-y-6">
      {/* Automation health summary */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <CheckCircle2 size={22} className="text-emerald-400" />
          </div>
          <div>
            <p className="text-3xl font-bold text-white">{okCount}</p>
            <p className="text-gray-500 text-sm">Automations OK</p>
          </div>
        </div>
        <div className="card flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-yellow-500/10 flex items-center justify-center">
            <AlertTriangle size={22} className="text-yellow-400" />
          </div>
          <div>
            <p className="text-3xl font-bold text-white">{warningCount}</p>
            <p className="text-gray-500 text-sm">Warnings</p>
          </div>
        </div>
        <div className="card flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-red-500/10 flex items-center justify-center">
            <XCircle size={22} className="text-red-400" />
          </div>
          <div>
            <p className="text-3xl font-bold text-white">{failedCount}</p>
            <p className="text-gray-500 text-sm">Failed</p>
          </div>
        </div>
      </div>

      {/* Automation status panel */}
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h2 className="text-white font-semibold">Automation Health</h2>
            <p className="text-gray-500 text-xs mt-0.5">All running automations and their last execution time</p>
          </div>
          <button className="btn-ghost flex items-center gap-1.5 text-xs">
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
        <div>
          {automations.map(a => (
            <AutomationRow key={a.name} {...a} />
          ))}
        </div>
      </div>

      {/* Carrier compliance table */}
      <div className="card overflow-hidden p-0">
        <div className="p-5 border-b border-gray-800 flex items-center justify-between gap-4">
          <div>
            <h2 className="text-white font-semibold">Carrier Compliance Status</h2>
            <p className="text-gray-500 text-xs mt-0.5">Insurance, ELD sync, and HOS status per carrier</p>
          </div>
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              className="input pl-9 w-52"
              placeholder="Search carriers…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>
        {isLoading ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  {['Carrier', 'Status', 'Insurance', 'Safety', 'ELD Sync', 'HOS'].map(h => (
                    <th key={h} className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-12 text-center text-gray-600 text-sm">No carriers found</td>
                  </tr>
                ) : (
                  items.map(c => <ComplianceRow key={c.id} carrier={c} />)
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
