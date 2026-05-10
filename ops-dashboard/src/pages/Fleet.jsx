import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fleet } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import Spinner from '../components/Spinner'
import Empty from '../components/Empty'
import { Search, Truck, MapPin, Fuel, Gauge, X, Activity } from 'lucide-react'

const trailerColors = {
  dry_van:        'bg-blue-500/10 text-blue-400',
  reefer:         'bg-cyan-500/10 text-cyan-400',
  flatbed:        'bg-orange-500/10 text-orange-400',
  step_deck:      'bg-orange-500/10 text-orange-400',
  box26:          'bg-purple-500/10 text-purple-400',
  cargo_van:      'bg-purple-500/10 text-purple-400',
  tanker_hazmat:  'bg-red-500/10 text-red-400',
  hotshot:        'bg-yellow-500/10 text-yellow-400',
  auto:           'bg-pink-500/10 text-pink-400',
}

function TruckModal({ truck, onClose }) {
  if (!truck) return null
  const loc = truck.current_location
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-xl shadow-2xl">
        <div className="flex items-start justify-between p-6 border-b border-gray-800">
          <div>
            <h2 className="text-white font-bold text-xl">Truck #{truck.truck_id}</h2>
            <div className="flex items-center gap-3 mt-1">
              <StatusBadge status={truck.status} />
              <span className="text-gray-500 text-xs capitalize">{truck.trailer_type?.replace(/_/g, ' ') || 'Unknown'}</span>
            </div>
          </div>
          <button onClick={onClose} className="btn-ghost p-2"><X size={18} /></button>
        </div>
        <div className="p-6 space-y-6">
          <div className="grid grid-cols-2 gap-4">
            <Stat label="Year"          value={truck.year} />
            <Stat label="Make"          value={truck.make} />
            <Stat label="Model"         value={truck.model} />
            <Stat label="VIN"           value={truck.vin} />
            <Stat label="Max Weight"    value={truck.max_weight_lbs ? `${truck.max_weight_lbs.toLocaleString()} lbs` : null} />
            <Stat label="Equipment Qty" value={truck.equipment_count} />
          </div>
          {loc && (
            <div className="card-sm">
              <p className="text-xs text-gray-500 mb-2 flex items-center gap-1.5"><MapPin size={12} /> Last Known Location</p>
              <p className="text-gray-200 text-sm">
                {loc.city ? `${loc.city}, ${loc.state}` : `${loc.lat?.toFixed(4)}°N, ${loc.lng?.toFixed(4)}°W`}
              </p>
              {truck.last_hos_update && (
                <p className="text-gray-500 text-xs mt-1">Updated: {new Date(truck.last_hos_update).toLocaleString()}</p>
              )}
            </div>
          )}
          <p className="text-xs text-gray-600">ID: {truck.id}</p>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <p className="text-gray-500 text-xs mb-0.5">{label}</p>
      <p className="text-gray-200 text-sm">{value || '—'}</p>
    </div>
  )
}

export default function Fleet() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [trailerFilter, setTrailerFilter] = useState('')
  const [selected, setSelected] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['fleet', statusFilter],
    queryFn: () => fleet.list(statusFilter ? { status: statusFilter } : {}),
    retry: false,
  })

  const items = (data?.items || []).filter(t => {
    if (search && !`${t.truck_id} ${t.make} ${t.model} ${t.vin}`.toLowerCase().includes(search.toLowerCase())) return false
    if (trailerFilter && t.trailer_type !== trailerFilter) return false
    return true
  })

  const all = data?.items || []
  const stats = {
    total:      all.length,
    available:  all.filter(t => t.status === 'available').length,
    on_load:    all.filter(t => t.status === 'on_load').length,
    maintenance:all.filter(t => t.status === 'maintenance').length,
    oos:        all.filter(t => t.status === 'out_of_service').length,
  }

  const trailerTypes = [...new Set(all.map(t => t.trailer_type).filter(Boolean))]

  return (
    <div className="space-y-5">
      {/* Stats */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { label: 'Total Trucks', count: stats.total, color: 'text-white' },
          { label: 'Available',    count: stats.available, color: 'text-emerald-400' },
          { label: 'On Load',      count: stats.on_load, color: 'text-blue-400' },
          { label: 'Maintenance',  count: stats.maintenance, color: 'text-yellow-400' },
          { label: 'Out of Svc',   count: stats.oos, color: 'text-red-400' },
        ].map(({ label, count, color }) => (
          <div key={label} className="card-sm text-center">
            <p className={`text-2xl font-bold ${color}`}>{count}</p>
            <p className="text-gray-500 text-xs mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="card p-4 flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            className="input w-full pl-9"
            placeholder="Search truck ID, VIN, make, model…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <select className="input" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="">All Statuses</option>
          <option value="available">Available</option>
          <option value="on_load">On Load</option>
          <option value="maintenance">Maintenance</option>
          <option value="out_of_service">Out of Service</option>
        </select>
        <select className="input" value={trailerFilter} onChange={e => setTrailerFilter(e.target.value)}>
          <option value="">All Types</option>
          {trailerTypes.map(t => <option key={t} value={t}>{t.replace(/_/g,' ')}</option>)}
        </select>
        <span className="text-gray-500 text-sm">{items.length} trucks</span>
      </div>

      {/* Grid */}
      {isLoading ? <Spinner /> : items.length === 0 ? (
        <div className="card"><Empty icon={Truck} title="No trucks found" sub="Try adjusting your filters" /></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {items.map(t => (
            <div
              key={t.id}
              className="card cursor-pointer hover:border-gray-600 transition-colors"
              onClick={() => setSelected(t)}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-gray-800 flex items-center justify-center">
                    <Truck size={18} className="text-gray-400" />
                  </div>
                  <div>
                    <p className="text-white font-semibold">#{t.truck_id}</p>
                    <p className="text-gray-500 text-xs">{t.year} {t.make} {t.model}</p>
                  </div>
                </div>
                <StatusBadge status={t.status} />
              </div>

              <div className="grid grid-cols-2 gap-2 mt-3">
                <div className="bg-gray-800/50 rounded-lg px-3 py-2">
                  <p className="text-gray-500 text-xs mb-0.5">Type</p>
                  <p className="text-gray-200 text-xs font-medium capitalize">
                    {t.trailer_type?.replace(/_/g,' ') || '—'}
                  </p>
                </div>
                <div className="bg-gray-800/50 rounded-lg px-3 py-2">
                  <p className="text-gray-500 text-xs mb-0.5">Max Weight</p>
                  <p className="text-gray-200 text-xs font-medium">
                    {t.max_weight_lbs ? `${(t.max_weight_lbs/1000).toFixed(0)}K lbs` : '—'}
                  </p>
                </div>
              </div>

              {t.current_location && (
                <div className="flex items-center gap-1.5 mt-3 text-gray-500 text-xs">
                  <MapPin size={11} />
                  <span>
                    {t.current_location.city
                      ? `${t.current_location.city}, ${t.current_location.state}`
                      : 'Location tracked'}
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {selected && <TruckModal truck={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
