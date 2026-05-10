import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboard, email } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import Spinner from '../components/Spinner'
import Empty from '../components/Empty'
import { Search, Package, MapPin, DollarSign, Clock, Mail, ArrowRight, X, RefreshCw } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'

function LoadModal({ load, onClose }) {
  if (!load) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-xl shadow-2xl">
        <div className="flex items-start justify-between p-6 border-b border-gray-800">
          <div>
            <h2 className="text-white font-bold text-lg">Load #{load.load_number || load.id?.slice(0,8)}</h2>
            <div className="flex items-center gap-3 mt-1">
              <StatusBadge status={load.status} />
              <span className="text-gray-500 text-xs">{load.broker_name}</span>
            </div>
          </div>
          <button onClick={onClose} className="btn-ghost p-2"><X size={18} /></button>
        </div>
        <div className="p-6 space-y-5">
          <div className="flex items-center gap-4">
            <div className="flex-1 card-sm">
              <p className="text-gray-500 text-xs mb-1">Origin</p>
              <p className="text-white font-medium">{load.origin_city}, {load.origin_state}</p>
            </div>
            <ArrowRight size={20} className="text-gray-600 flex-shrink-0" />
            <div className="flex-1 card-sm">
              <p className="text-gray-500 text-xs mb-1">Destination</p>
              <p className="text-white font-medium">{load.dest_city}, {load.dest_state}</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="card-sm text-center">
              <p className="text-gray-500 text-xs mb-1">Rate</p>
              <p className="text-white font-bold text-lg">${(load.rate_total||0).toLocaleString()}</p>
            </div>
            <div className="card-sm text-center">
              <p className="text-gray-500 text-xs mb-1">$/Mile</p>
              <p className="text-white font-bold text-lg">{load.rate_per_mile ? `$${load.rate_per_mile}` : '—'}</p>
            </div>
            <div className="card-sm text-center">
              <p className="text-gray-500 text-xs mb-1">Miles</p>
              <p className="text-white font-bold text-lg">{load.miles || '—'}</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><p className="text-gray-500 text-xs">Broker Phone</p><p className="text-gray-200">{load.broker_phone || '—'}</p></div>
            <div><p className="text-gray-500 text-xs">Commodity</p><p className="text-gray-200">{load.commodity || '—'}</p></div>
            <div><p className="text-gray-500 text-xs">Equipment</p><p className="text-gray-200">{load.equipment_type || '—'}</p></div>
            <div><p className="text-gray-500 text-xs">Weight</p><p className="text-gray-200">{load.weight ? `${load.weight.toLocaleString()} lbs` : '—'}</p></div>
            <div><p className="text-gray-500 text-xs">Pickup</p><p className="text-gray-200">{load.pickup_at ? new Date(load.pickup_at).toLocaleDateString() : '—'}</p></div>
            <div><p className="text-gray-500 text-xs">Delivery</p><p className="text-gray-200">{load.delivery_at ? new Date(load.delivery_at).toLocaleDateString() : '—'}</p></div>
          </div>
          {load.special_instructions && (
            <div className="card-sm">
              <p className="text-gray-500 text-xs mb-1">Special Instructions</p>
              <p className="text-gray-200 text-sm">{load.special_instructions}</p>
            </div>
          )}
          <p className="text-xs text-gray-600">ID: {load.id}</p>
        </div>
      </div>
    </div>
  )
}

export default function Dispatch() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [selected, setSelected] = useState(null)
  const [activeTab, setActiveTab] = useState('loads')

  const { data: loadsData, isLoading: loadsLoading } = useQuery({
    queryKey: ['recent-loads-all'],
    queryFn: () => dashboard.recentLoads(50),
    retry: false,
  })
  const { data: emailData, isLoading: emailLoading } = useQuery({
    queryKey: ['email-log'],
    queryFn: () => email.log({ limit: 50 }),
    retry: false,
  })

  const pollMut = useMutation({
    mutationFn: email.pollImap,
  })

  const loads = (loadsData?.items || []).filter(l => {
    if (statusFilter && l.status !== statusFilter) return false
    if (search) {
      const q = search.toLowerCase()
      return [l.broker_name, l.load_number, l.origin_city, l.dest_city].some(v => v?.toLowerCase().includes(q))
    }
    return true
  })

  const emails = emailData?.data || []

  return (
    <div className="space-y-5">
      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-gray-800">
        {[
          { key: 'loads',  label: 'Loads', count: loadsData?.items?.length },
          { key: 'emails', label: 'Email Ingest', count: emails.length },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === t.key
                ? 'text-white border-brand-500'
                : 'text-gray-500 border-transparent hover:text-gray-300'
            }`}
          >
            {t.label}
            {t.count !== undefined && (
              <span className="ml-2 px-1.5 py-0.5 rounded text-xs bg-gray-800 text-gray-400">{t.count}</span>
            )}
          </button>
        ))}
      </div>

      {activeTab === 'loads' && (
        <>
          {/* Filters */}
          <div className="card p-4 flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 min-w-48">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                className="input w-full pl-9"
                placeholder="Search broker, load #, origin, destination…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
            <select className="input" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
              <option value="">All Statuses</option>
              <option value="available">Available</option>
              <option value="booked">Booked</option>
              <option value="in_transit">In Transit</option>
              <option value="delivered">Delivered</option>
            </select>
            <span className="text-gray-500 text-sm">{loads.length} loads</span>
          </div>

          {/* Table */}
          <div className="card overflow-hidden p-0">
            {loadsLoading ? <Spinner /> : loads.length === 0 ? (
              <Empty icon={Package} title="No loads found" sub="Loads appear here once rate confirmations are processed" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800">
                      {['Load #', 'Route', 'Broker', 'Rate', '$/Mile', 'Status', 'Created', ''].map(h => (
                        <th key={h} className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {loads.map(l => (
                      <tr key={l.id} className="table-row">
                        <td className="px-5 py-4 font-mono text-gray-400 text-xs">{l.load_number || l.id?.slice(0,8)}</td>
                        <td className="px-5 py-4">
                          <p className="text-gray-200 font-medium">{l.origin_city}, {l.origin_state}</p>
                          <p className="text-gray-500 text-xs flex items-center gap-1"><ArrowRight size={10}/>{l.dest_city}, {l.dest_state}</p>
                        </td>
                        <td className="px-5 py-4 text-gray-300">{l.broker_name || '—'}</td>
                        <td className="px-5 py-4 text-white font-semibold">${(l.rate_total||0).toLocaleString()}</td>
                        <td className="px-5 py-4 text-gray-400">{l.rate_per_mile ? `$${l.rate_per_mile}` : '—'}</td>
                        <td className="px-5 py-4"><StatusBadge status={l.status} /></td>
                        <td className="px-5 py-4 text-gray-500 text-xs">{l.created_at ? new Date(l.created_at).toLocaleDateString() : '—'}</td>
                        <td className="px-5 py-4">
                          <button onClick={() => setSelected(l)} className="btn-ghost text-xs px-3 py-1.5">View</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {activeTab === 'emails' && (
        <>
          <div className="card p-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Mail size={16} className="text-gray-400" />
              <span className="text-sm text-gray-300">{emails.length} emails processed</span>
            </div>
            <button
              onClick={() => pollMut.mutate()}
              disabled={pollMut.isPending}
              className="btn-primary flex items-center gap-2"
            >
              <RefreshCw size={14} className={pollMut.isPending ? 'animate-spin' : ''} />
              Poll IMAP Now
            </button>
          </div>

          <div className="card overflow-hidden p-0">
            {emailLoading ? <Spinner /> : emails.length === 0 ? (
              <Empty icon={Mail} title="No emails yet" sub="Emails processed via SendGrid webhook or Hostinger IMAP will appear here" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800">
                      {['From', 'Subject', 'Source', 'Attachments', 'Status', 'Received'].map(h => (
                        <th key={h} className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {emails.map(e => (
                      <tr key={e.id} className="table-row">
                        <td className="px-5 py-4 max-w-36 truncate text-gray-300 text-xs">{e.from_email}</td>
                        <td className="px-5 py-4 max-w-48">
                          <p className="text-gray-200 truncate">{e.subject || '(no subject)'}</p>
                          {e.broker_name && <p className="text-gray-500 text-xs">Broker: {e.broker_name}</p>}
                        </td>
                        <td className="px-5 py-4">
                          <span className={e.source === 'hostinger_imap' ? 'badge-purple' : 'badge-blue'}>
                            {e.source === 'hostinger_imap' ? 'IMAP' : 'SendGrid'}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-gray-400">{e.attachment_count || 0}</td>
                        <td className="px-5 py-4"><StatusBadge status={e.status} /></td>
                        <td className="px-5 py-4 text-gray-500 text-xs">
                          {e.received_at ? new Date(e.received_at).toLocaleString() : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {selected && <LoadModal load={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
