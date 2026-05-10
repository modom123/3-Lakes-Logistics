const map = {
  active:       'badge-green',
  available:    'badge-green',
  ok:           'badge-green',
  paid:         'badge-green',
  on_load:      'badge-blue',
  onboarding:   'badge-blue',
  syncing:      'badge-blue',
  in_transit:   'badge-blue',
  warning:      'badge-yellow',
  low_confidence:'badge-yellow',
  maintenance:  'badge-yellow',
  unpaid:       'badge-yellow',
  suspended:    'badge-red',
  out_of_service:'badge-red',
  failed:       'badge-red',
  error:        'badge-red',
  overdue:      'badge-red',
  churned:      'badge-gray',
  unknown:      'badge-gray',
}

const labels = {
  on_load:       'On Load',
  out_of_service:'Out of Service',
  low_confidence:'Low Confidence',
  in_transit:    'In Transit',
}

export default function StatusBadge({ status }) {
  const cls = map[(status || '').toLowerCase()] || 'badge-gray'
  const label = labels[(status || '').toLowerCase()] || status
  return (
    <span className={cls}>
      <span className="w-1.5 h-1.5 rounded-full bg-current inline-block" />
      {label}
    </span>
  )
}
