import { Routes, Route, Navigate } from 'react-router-dom'
import Navbar from './components/Navbar'
import Dashboard from './pages/Dashboard'
import NewInspection from './pages/NewInspection'
import InspectionDetail from './pages/InspectionDetail'

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/inspect" element={<NewInspection />} />
          <Route path="/inspection/:id" element={<InspectionDetail />} />
        </Routes>
      </main>
    </div>
  )
}
