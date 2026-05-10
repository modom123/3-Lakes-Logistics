import { useQuery } from '@tanstack/react-query'
import { dashboard, carriers, fleet, mockRevenue } from '../api/client'
import KpiCard from '../components/KpiCard'
import Spinner from '../components/Spinner'
import {
  BarChart3, TrendingUp, Truck, Users, Package,
  DollarSign, Target, Activity
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, PieChart, Pie, Cell,
  Legend, AreaChart, Area
} from 'recharts'

const COLORS = ['#2a8af6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']

const weeklyLoads = [
  { week: 'W1', loads: 28, revenue: 52000 },
  { week: 'W2', loads: 34, revenue: 63000 },
  { week: 'W3', loads: 29, revenue: 55000 },
  { week: 'W4', loads: 41, revenue: 78000 },
  { week: 'W5', loads: 38, revenue: 71000 },
  { week: 'W6', loads: 44, revenue: 83000 },
  { week: 'W7', loads: 47, revenue: 89000 },
  { week: 'W8', loads: 42, revenue: 79000 },
]

const trailerMix = [
  { name: 'Dry Van',   value: 42 },
  { name: 'Reefer',    value: 18 },
  { name: 'Flatbed',   value: 15 },
  { name: 'Box Truck', value: 12 },
  { name: 'Cargo Van', value: 8  },
  { name: 'Hotshot',   value: 5  },
]

const topCarriers = [
  { name: 'Sunshine Freight',  loads: 24, revenue: 58000, rpm: 2.4 },
  { name: 'Big Rig Express',   loads: 19, revenue: 44000, rpm: 2.1 },
  { name: 'Eagle Transport',   loads: 17, revenue: 39000, rpm: 2.3 },
  { name: 'Atlas Freight',     loads: 15, revenue: 36000, rpm: 2.5 },
  { name: 'Prime Logistics',   loads: 12, revenue: 27000, rpm: 1.9 },
]

const utilizationData = [
  { month: 'Nov', rate: 72 },
  { month: 'Dec', rate: 78 },
  { month: 'Jan', rate: 65 },
  { month: 'Feb', rate: 82 },
  { month: 'Mar', rate: 88 },
  { month: 'Apr', rate: 85 },
  { month: 'May', rate: 87 },
]

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 text-xs">
      <p className="text-gray-400 mb-1">{label}</p>
      {payload.map(p => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {typeof p.value === 'number' && p.value > 100 ? `$${p.value.toLocaleString()}` : p.value}
          {p.name === 'rate' ? '%' : ''}
        </p>
      ))}
    </div>
  )
}

export default function Analytics() {
  const { data: kpis } = useQuery({ queryKey: ['kpis'], queryFn: dashboard.kpis, retry: false })
  const { data: carriersData } = useQuery({ queryKey: ['carriers'], queryFn: () => carriers.list(), retry: false })
  const { data: fleetData } = useQuery({ queryKey: ['fleet'], queryFn: () => fleet.list(), retry: false })
  const revenue = mockRevenue()

  const totalCarriers = carriersData?.count || 0
  const totalTrucks   = fleetData?.count || 0
  const activeCarriers = (carriersData?.items || []).filter(c => c.status === 'active').length

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Fleet Utilization"
          value="87%"
          sub="+5% vs last month"
          trend="up"
          icon={Truck}
          color="green"
        />
        <KpiCard
          label="Avg $/Mile"
          value={kpis?.avg_rpm ? `$${kpis.avg_rpm}` : '$2.28'}
          sub="Industry avg: $2.10"
          trend="up"
          icon={TrendingUp}
          color="blue"
        />
        <KpiCard
          label="Active Carriers"
          value={activeCarriers || 38}
          sub={`${totalCarriers || 42} total`}
          trend="up"
          icon={Users}
          color="purple"
        />
        <KpiCard
          label="Total Fleet"
          value={totalTrucks || 127}
          sub={`Across ${totalCarriers || 42} carriers`}
          trend="up"
          icon={Truck}
          color="yellow"
        />
      </div>

      {/* Charts row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-white font-semibold mb-1">Weekly Load Volume & Revenue</h3>
          <p className="text-gray-500 text-xs mb-4">Last 8 weeks</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={weeklyLoads} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
              <XAxis dataKey="week" tick={{ fill:'#6b7280', fontSize:11 }} axisLine={false} tickLine={false} />
              <YAxis yAxisId="left" tick={{ fill:'#6b7280', fontSize:11 }} axisLine={false} tickLine={false} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill:'#6b7280', fontSize:11 }} axisLine={false} tickLine={false}
                tickFormatter={v => `$${(v/1000).toFixed(0)}K`} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />
              <Bar yAxisId="left"  dataKey="loads"   name="Loads"   fill="#2a8af6" radius={[3,3,0,0]} />
              <Bar yAxisId="right" dataKey="revenue" name="Revenue" fill="#10b981" radius={[3,3,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="text-white font-semibold mb-1">Fleet Utilization Rate</h3>
          <p className="text-gray-500 text-xs mb-4">% of trucks on active loads per month</p>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={utilizationData} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
              <defs>
                <linearGradient id="utilGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="month" tick={{ fill:'#6b7280', fontSize:11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:'#6b7280', fontSize:11 }} axisLine={false} tickLine={false}
                tickFormatter={v => `${v}%`} domain={[0,100]} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="rate" name="rate" stroke="#10b981" strokeWidth={2} fill="url(#utilGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Charts row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Trailer mix */}
        <div className="card">
          <h3 className="text-white font-semibold mb-1">Fleet by Trailer Type</h3>
          <p className="text-gray-500 text-xs mb-4">Total truck count by equipment</p>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={trailerMix} cx="50%" cy="50%" outerRadius={70} dataKey="value" nameKey="name">
                {trailerMix.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background:'#111827', border:'1px solid #1f2937', borderRadius:'8px', fontSize:11 }} />
              <Legend
                wrapperStyle={{ fontSize: 11, color: '#9ca3af' }}
                iconSize={8}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Top carriers */}
        <div className="card lg:col-span-2">
          <h3 className="text-white font-semibold mb-1">Top Carriers by Revenue (MTD)</h3>
          <p className="text-gray-500 text-xs mb-4">Performance ranking this month</p>
          <div className="space-y-0">
            {topCarriers.map((c, i) => (
              <div key={c.name} className="flex items-center gap-4 py-3 border-b border-gray-800 last:border-0">
                <div className="w-6 h-6 rounded-full bg-gray-800 flex items-center justify-center text-xs font-bold text-gray-400">
                  {i + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-gray-200 text-sm font-medium">{c.name}</p>
                    <p className="text-white font-semibold text-sm">${c.revenue.toLocaleString()}</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-brand-500"
                        style={{ width: `${(c.revenue / topCarriers[0].revenue) * 100}%` }}
                      />
                    </div>
                    <span className="text-gray-500 text-xs">{c.loads} loads</span>
                    <span className="text-gray-500 text-xs">${c.rpm}/mi</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
