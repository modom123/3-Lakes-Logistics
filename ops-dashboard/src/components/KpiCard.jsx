import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

export default function KpiCard({ label, value, sub, trend, icon: Icon, color = 'blue' }) {
  const colors = {
    blue:   'text-brand-400 bg-brand-500/10',
    green:  'text-emerald-400 bg-emerald-500/10',
    yellow: 'text-yellow-400 bg-yellow-500/10',
    red:    'text-red-400 bg-red-500/10',
    purple: 'text-purple-400 bg-purple-500/10',
  }

  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus
  const trendColor = trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-red-400' : 'text-gray-500'

  return (
    <div className="card flex flex-col gap-4">
      <div className="flex items-start justify-between">
        <p className="text-gray-400 text-sm font-medium">{label}</p>
        {Icon && (
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${colors[color]}`}>
            <Icon size={18} />
          </div>
        )}
      </div>
      <div>
        <p className="text-2xl font-bold text-white tracking-tight">{value}</p>
        {(sub || trend) && (
          <div className="flex items-center gap-1.5 mt-1">
            {trend && <TrendIcon size={13} className={trendColor} />}
            <p className="text-gray-500 text-xs">{sub}</p>
          </div>
        )}
      </div>
    </div>
  )
}
