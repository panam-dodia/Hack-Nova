import { Link, useLocation } from 'react-router-dom'
import { HardHat, LayoutDashboard, PlusCircle, Mic } from 'lucide-react'
import { useState } from 'react'
import VoiceAssistant from './VoiceAssistant'
import clsx from 'clsx'

export default function Navbar() {
  const { pathname } = useLocation()
  const [voiceOpen, setVoiceOpen] = useState(false)

  const navLink = (to: string, label: string, icon: React.ReactNode) => (
    <Link
      to={to}
      className={clsx(
        'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
        pathname === to
          ? 'bg-blue-50 text-blue-700'
          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
      )}
    >
      {icon}
      {label}
    </Link>
  )

  return (
    <>
      <nav className="bg-white border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <Link to="/dashboard" className="flex items-center gap-2.5">
              <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                <HardHat className="w-5 h-5 text-white" />
              </div>
              <span className="font-bold text-gray-900 text-lg">SafetyAI</span>
              <span className="hidden sm:block text-xs text-gray-400 font-normal mt-0.5">
                Powered by Amazon Nova
              </span>
            </Link>

            {/* Nav links */}
            <div className="flex items-center gap-1">
              {navLink('/dashboard', 'Dashboard', <LayoutDashboard className="w-4 h-4" />)}
              {navLink('/inspect', 'New Inspection', <PlusCircle className="w-4 h-4" />)}

              <button
                onClick={() => setVoiceOpen(true)}
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900 transition-colors"
              >
                <Mic className="w-4 h-4" />
                <span className="hidden sm:inline">Voice Mode</span>
              </button>
            </div>
          </div>
        </div>
      </nav>

      {voiceOpen && <VoiceAssistant onClose={() => setVoiceOpen(false)} />}
    </>
  )
}
