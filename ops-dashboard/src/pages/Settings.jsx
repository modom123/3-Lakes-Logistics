import { useState } from 'react'
import { Settings, Mail, Zap, Bell, Shield, Key, CheckCircle2 } from 'lucide-react'

function Section({ title, icon: Icon, children }) {
  return (
    <div className="card space-y-4">
      <div className="flex items-center gap-3 pb-3 border-b border-gray-800">
        <div className="w-8 h-8 rounded-lg bg-brand-500/10 flex items-center justify-center">
          <Icon size={16} className="text-brand-400" />
        </div>
        <h2 className="text-white font-semibold">{title}</h2>
      </div>
      {children}
    </div>
  )
}

function Field({ label, value, type = 'text', placeholder, saved }) {
  const [v, setV] = useState(value || '')
  return (
    <div>
      <label className="text-xs text-gray-500 block mb-1.5">{label}</label>
      <div className="flex gap-2">
        <input
          type={type}
          className="input flex-1"
          value={v}
          placeholder={placeholder}
          onChange={e => setV(e.target.value)}
        />
        {saved && <span className="flex items-center text-emerald-400 text-xs gap-1"><CheckCircle2 size={13} />Saved</span>}
      </div>
    </div>
  )
}

export default function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <Section title="Email Integration" icon={Mail}>
        <div className="space-y-4">
          <p className="text-gray-500 text-sm">Dual-channel email configured: SendGrid (brokers) + Hostinger IMAP (internal)</p>
          <Field label="SendGrid API Key" value="" type="password" placeholder="SG.xxx…" />
          <Field label="SendGrid Inbound Email" value="loads@3lakeslogistics.com" saved />
          <hr className="border-gray-800" />
          <Field label="Hostinger IMAP Email" value="info@3lakeslogistics.com" saved />
          <Field label="Hostinger IMAP Password" value="" type="password" placeholder="••••••••" />
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="text-emerald-400 text-sm">IMAP polling active — every 5 minutes</span>
          </div>
        </div>
        <button className="btn-primary">Save Email Settings</button>
      </Section>

      <Section title="Automation Settings" icon={Zap}>
        <div className="space-y-3">
          {[
            { label: 'ELD Sync Interval', value: '5 minutes', desc: 'How often to sync ELD data from Motive/Samsara' },
            { label: 'GPS Update Interval', value: '30 seconds', desc: 'Truck location update frequency' },
            { label: 'IMAP Poll Interval', value: '5 minutes', desc: 'How often to check Hostinger inbox' },
            { label: 'Compliance Check Schedule', value: 'Daily 06:00 UTC', desc: 'Automated compliance sweep time' },
          ].map(({ label, value, desc }) => (
            <div key={label} className="flex items-start justify-between gap-4 py-2">
              <div>
                <p className="text-gray-200 text-sm font-medium">{label}</p>
                <p className="text-gray-500 text-xs mt-0.5">{desc}</p>
              </div>
              <span className="badge-blue flex-shrink-0 mt-0.5">{value}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="API Configuration" icon={Key}>
        <div className="space-y-4">
          <Field label="API Bearer Token" value="" type="password" placeholder="change-me-in-prod" />
          <Field label="Supabase URL" value="" placeholder="https://xxx.supabase.co" />
          <Field label="Anthropic API Key" value="" type="password" placeholder="sk-ant-xxx" />
          <Field label="Stripe Secret Key" value="" type="password" placeholder="sk_live_xxx" />
        </div>
        <button className="btn-primary">Save API Keys</button>
      </Section>

      <Section title="Notifications" icon={Bell}>
        <div className="space-y-3">
          {[
            'Automation failure alerts',
            'New load created from email',
            'Invoice overdue (7+ days)',
            'ELD sync failure',
            'HOS violation detected',
            'New carrier onboarded',
          ].map(n => (
            <div key={n} className="flex items-center justify-between py-1">
              <span className="text-gray-300 text-sm">{n}</span>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" defaultChecked className="sr-only peer" />
                <div className="w-9 h-5 bg-gray-700 rounded-full peer peer-checked:bg-brand-600 after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4" />
              </label>
            </div>
          ))}
        </div>
      </Section>
    </div>
  )
}
