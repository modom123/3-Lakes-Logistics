import { Bell, Search, RefreshCw } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

const titles = {
  '/':           { title: 'Dashboard',  sub: 'Business Overview' },
  '/carriers':   { title: 'Carriers',   sub: 'Carrier Management' },
  '/fleet':      { title: 'Fleet',      sub: 'Trucks & Equipment' },
  '/dispatch':   { title: 'Dispatch',   sub: 'Load Management' },
  '/financials': { title: 'Financials', sub: 'Revenue & Invoicing' },
  '/compliance': { title: 'Compliance', sub: 'Automation & Safety' },
  '/analytics':  { title: 'Analytics',  sub: 'Performance Metrics' },
}

export default function Header() {
  const { pathname } = useLocation()
  const qc = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)
  const { title, sub } = titles[pathname] || { title: pathname.slice(1), sub: '' }

  const refresh = () => {
    setRefreshing(true)
    qc.invalidateQueries()
    setTimeout(() => setRefreshing(false), 800)
  }

  const now = new Date().toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
  })

  return (
    <header className="h-16 flex-shrink-0 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-6">
      <div>
        <h1 className="text-white font-semibold text-lg leading-tight">{title}</h1>
        <p className="text-gray-500 text-xs">{now} · {sub}</p>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={refresh}
          className="btn-ghost flex items-center gap-1.5"
          title="Refresh data"
        >
          <RefreshCw size={15} className={refreshing ? 'animate-spin' : ''} />
          Refresh
        </button>

        <div className="relative">
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-red-500" />
          <button className="btn-ghost p-2">
            <Bell size={16} />
          </button>
        </div>

        <div className="flex items-center gap-2 pl-2 border-l border-gray-700">
          <div className="w-7 h-7 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white">
            3L
          </div>
          <span className="text-sm text-gray-300 font-medium">Admin</span>
        </div>
      </div>
    </header>
  )
}
