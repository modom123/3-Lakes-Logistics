export default function Empty({ icon: Icon, title, sub }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {Icon && <Icon size={32} className="text-gray-700 mb-3" />}
      <p className="text-gray-400 font-medium">{title}</p>
      {sub && <p className="text-gray-600 text-sm mt-1">{sub}</p>}
    </div>
  )
}
