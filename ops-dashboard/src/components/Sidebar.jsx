import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Truck, Users, Package,
  DollarSign, ShieldCheck, BarChart3, Mail,
  Settings, ChevronRight
} from 'lucide-react'

const nav = [
  { to: '/',            icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/carriers',    icon: Users,           label: 'Carriers' },
  { to: '/fleet',       icon: Truck,           label: 'Fleet' },
  { to: '/dispatch',    icon: Package,         label: 'Dispatch' },
  { to: '/financials',  icon: DollarSign,      label: 'Financials' },
  { to: '/compliance',  icon: ShieldCheck,     label: 'Compliance' },
  { to: '/analytics',   icon: BarChart3,       label: 'Analytics' },
]

export default function Sidebar() {
  return (
    <aside className="w-60 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center text-white font-bold text-sm">
            3L
          </div>
          <div>
            <p className="text-white font-semibold text-sm leading-tight">3 Lakes Logistics</p>
            <p className="text-gray-500 text-xs">Command Center</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {nav.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors group ${
                isActive
                  ? 'bg-brand-600/20 text-brand-400 font-medium'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`
            }
          >
            <Icon size={17} />
            <span className="flex-1">{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-3 py-4 border-t border-gray-800 space-y-0.5">
        <NavLink
          to="/settings"
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
        >
          <Settings size={17} />
          Settings
        </NavLink>
        <div className="px-3 py-3">
          <div className="text-xs text-gray-600">v1.0.0 · ops-suite</div>
        </div>
      </div>
    </aside>
  )
}
