import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Layout from './components/Layout'
import Dashboard  from './pages/Dashboard'
import Carriers   from './pages/Carriers'
import Fleet      from './pages/Fleet'
import Dispatch   from './pages/Dispatch'
import Financials from './pages/Financials'
import Compliance from './pages/Compliance'
import Analytics  from './pages/Analytics'
import Settings   from './pages/Settings'

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime:    300_000,
      refetchOnWindowFocus: false,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index       element={<Dashboard />}  />
            <Route path="carriers"   element={<Carriers />}   />
            <Route path="fleet"      element={<Fleet />}      />
            <Route path="dispatch"   element={<Dispatch />}   />
            <Route path="financials" element={<Financials />} />
            <Route path="compliance" element={<Compliance />} />
            <Route path="analytics"  element={<Analytics />}  />
            <Route path="settings"   element={<Settings />}   />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
