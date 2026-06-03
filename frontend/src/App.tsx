import { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { queryClient } from './api/client'
import { Layout } from './components/layout/Layout'
import { PageLoader } from './components/ui/Spinner'

const Login        = lazy(() => import('./pages/Login'))
const Dashboard    = lazy(() => import('./pages/Dashboard'))
const QueryConsole = lazy(() => import('./pages/QueryConsole'))
const Incidents    = lazy(() => import('./pages/Incidents'))
const Suppliers    = lazy(() => import('./pages/Suppliers'))
const DataSources  = lazy(() => import('./pages/DataSources'))
const Observability= lazy(() => import('./pages/Observability'))
const Architecture = lazy(() => import('./pages/Architecture'))

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><PageLoader /></div>}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="query" element={<QueryConsole />} />
              <Route path="incidents" element={<Incidents />} />
              <Route path="suppliers" element={<Suppliers />} />
              <Route path="data-sources" element={<DataSources />} />
              <Route path="observability" element={<Observability />} />
              <Route path="architecture" element={<Architecture />} />
              <Route path="settings" element={<div className="p-6 text-slate-500">Settings coming soon.</div>} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          className: 'font-sans text-sm',
          success: { iconTheme: { primary: '#10B981', secondary: 'white' } },
          error:   { iconTheme: { primary: '#EF4444', secondary: 'white' } },
        }}
      />
    </QueryClientProvider>
  )
}
