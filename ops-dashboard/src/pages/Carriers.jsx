import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { carriers } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import Spinner from '../components/Spinner'
import Empty from '../components/Empty'
import {
  Search, Users, Building2, Phone, Mail, Hash,
  Truck, DollarSign, ChevronDown, MoreHorizontal,
  ExternalLink, X
} from 'lucide-react'

function CarrierModal({ carrier, onClose }) {
  const qc = useQueryClient()
  const mut = useMutation({
    mutationFn: ({ id, status }) => carriers.setStatus(id, status),
    onSuccess: () => { qc.invalidateQueries(['carriers']); onClose() },
  })
  if (!carrier) return null

  const statuses = ['onboarding', 'active', 'suspended', 'churned']

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-gray-800">
          <div>
            <h2 className="text-white font-bold text-xl">{carrier.company_name}</h2>
            <div className="flex items-center gap-3 mt-1">
              <StatusBadge status={carrier.status} />
              <span className="text-gray-500 text-xs">Plan: {carrier.plan || 'standard'}</span>
            </div>
          </div>
          <button onClick={onClose} className="btn-ghost p-2"><X size={18} /></button>
        </div>

        {/* Body */}
        <div className="p-6 grid grid-cols-2 gap-6">
          <div className="space-y-4">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Company Info</h3>
            <InfoRow icon={Hash}      label="DOT #"     value={carrier.dot_number} />
            <InfoRow icon={Hash}      label="MC #"      value={carrier.mc_number} />
            <InfoRow icon={Building2} label="Entity"    value={carrier.legal_entity} />
            <InfoRow icon={Hash}      label="EIN"       value={carrier.ein} />
            <InfoRow icon={Phone}     label="Phone"     value={carrier.phone} />
            <InfoRow icon={Mail}      label="Email"     value={carrier.email} />
          </div>
          <div className="space-y-4">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Account</h3>
            <InfoRow icon={DollarSign} label="Stripe"   value={carrier.stripe_customer_id ? 'Connected' : 'Not connected'} />
            <InfoRow icon={Building2} label="Address"   value={carrier.address} />
            <InfoRow icon={Users}     label="Years"     value={carrier.years_in_business ? `${carrier.years_in_business} years` : null} />
            <div>
              <p className="text-xs text-gray-500 mb-1.5">Change Status</p>
              <div className="flex flex-wrap gap-2">
                {statuses.map(s => (
                  <button
                    key={s}
                    disabled={carrier.status === s || mut.isPending}
                    onClick={() => mut.mutate({ id: carrier.id, status: s })}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                      carrier.status === s
                        ? 'border-brand-500 text-brand-400 bg-brand-500/10 cursor-default'
                        : 'border-gray-700 text-gray-400 hover:border-gray-600 hover:text-white'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="px-6 pb-6 text-xs text-gray-600">
          ID: {carrier.id} · Joined: {carrier.created_at ? new Date(carrier.created_at).toLocaleDateString() : '—'}
        </div>
      </div>
    </div>
  )
}

function InfoRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="w-7 h-7 rounded-md bg-gray-800 flex items-center justify-center flex-shrink-0">
        <Icon size={13} className="text-gray-400" />
      </div>
      <div className="min-w-0">
        <p className="text-gray-500 text-xs leading-none mb-0.5">{label}</p>
        <p className="text-gray-200 text-sm truncate">{value || '—'}</p>
      </div>
    </div>
  )
}

export default function Carriers() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [selected, setSelected] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['carriers', statusFilter],
    queryFn: () => carriers.list(statusFilter ? { status: statusFilter } : {}),
    retry: false,
  })

  const items = (data?.items || []).filter(c =>
    !search || [c.company_name, c.dot_number, c.mc_number, c.email]
      .some(v => v?.toLowerCase().includes(search.toLowerCase()))
  )

  const counts = { all: data?.count || 0 }
  ;['active','onboarding','suspended','churned'].forEach(s => {
    counts[s] = (data?.items || []).filter(c => c.status === s).length
  })

  return (
    <div className="space-y-5">
      {/* Stats strip */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { label: 'Total',       count: counts.all,        color: 'text-white' },
          { label: 'Active',      count: counts.active,     color: 'text-emerald-400' },
          { label: 'Onboarding',  count: counts.onboarding, color: 'text-blue-400' },
          { label: 'Suspended',   count: counts.suspended,  color: 'text-yellow-400' },
          { label: 'Churned',     count: counts.churned,    color: 'text-gray-500' },
        ].map(({ label, count, color }) => (
          <div key={label} className="card-sm text-center">
            <p className={`text-2xl font-bold ${color}`}>{count}</p>
            <p className="text-gray-500 text-xs mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="card p-4 flex items-center gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            className="input w-full pl-9"
            placeholder="Search carrier name, DOT#, MC#, email…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <select
          className="input"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
        >
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="onboarding">Onboarding</option>
          <option value="suspended">Suspended</option>
          <option value="churned">Churned</option>
        </select>
        <span className="text-gray-500 text-sm">{items.length} results</span>
      </div>

      {/* Table */}
      <div className="card overflow-hidden p-0">
        {isLoading ? <Spinner /> : items.length === 0 ? (
          <Empty icon={Users} title="No carriers found" sub="Try adjusting your search or filters" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  {['Company', 'DOT / MC', 'Contact', 'Plan', 'Status', 'Joined', ''].map(h => (
                    <th key={h} className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map(c => (
                  <tr key={c.id} className="table-row">
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-brand-500/10 flex items-center justify-center text-xs font-bold text-brand-400 flex-shrink-0">
                          {(c.company_name || 'U')[0].toUpperCase()}
                        </div>
                        <div>
                          <p className="text-gray-200 font-medium">{c.company_name}</p>
                          <p className="text-gray-600 text-xs">{c.legal_entity || 'LLC'}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <p className="text-gray-300">DOT {c.dot_number || '—'}</p>
                      <p className="text-gray-500 text-xs">MC {c.mc_number || '—'}</p>
                    </td>
                    <td className="px-5 py-4">
                      <p className="text-gray-300">{c.phone || '—'}</p>
                      <p className="text-gray-500 text-xs truncate max-w-36">{c.email || '—'}</p>
                    </td>
                    <td className="px-5 py-4">
                      <span className="badge-blue capitalize">{c.plan || 'standard'}</span>
                    </td>
                    <td className="px-5 py-4">
                      <StatusBadge status={c.status} />
                    </td>
                    <td className="px-5 py-4 text-gray-500 text-xs">
                      {c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-5 py-4">
                      <button
                        onClick={() => setSelected(c)}
                        className="btn-ghost text-xs px-3 py-1.5"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && <CarrierModal carrier={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
