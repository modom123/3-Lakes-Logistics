export default function Spinner({ className = '' }) {
  return (
    <div className={`flex items-center justify-center p-12 ${className}`}>
      <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}
