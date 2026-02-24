import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PlusCircle, AlertTriangle, CheckCircle, Clock, ChevronRight, Loader2 } from 'lucide-react'
import { format } from 'date-fns'
import clsx from 'clsx'
import { inspectionsApi } from '../api/client'
import type { Inspection, InspectionStatus } from '../types'

const STATUS_STYLES: Record<InspectionStatus, string> = {
  pending:   'text-gray-500 bg-gray-100',
  uploading: 'text-blue-600 bg-blue-100',
  analyzing: 'text-yellow-600 bg-yellow-100 analyzing-pulse',
  completed: 'text-green-600 bg-green-100',
  failed:    'text-red-600 bg-red-100',
}

const STATUS_ICONS: Record<InspectionStatus, React.ReactNode> = {
  pending:   <Clock className="w-3.5 h-3.5" />,
  uploading: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
  analyzing: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
  completed: <CheckCircle className="w-3.5 h-3.5" />,
  failed:    <AlertTriangle className="w-3.5 h-3.5" />,
}

function SeverityBar({ inspection }: { inspection: Inspection }) {
  const total = inspection.total_violations
  if (total === 0) return <span className="text-xs text-green-600 font-medium">No violations</span>

  const pct = (n: number) => `${Math.round((n / total) * 100)}%`
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex h-2 rounded-full overflow-hidden flex-1 bg-gray-100">
        {inspection.critical_count > 0 && (
          <div className="bg-red-500" style={{ width: pct(inspection.critical_count) }} />
        )}
        {inspection.high_count > 0 && (
          <div className="bg-orange-500" style={{ width: pct(inspection.high_count) }} />
        )}
        {inspection.medium_count > 0 && (
          <div className="bg-yellow-400" style={{ width: pct(inspection.medium_count) }} />
        )}
        {inspection.low_count > 0 && (
          <div className="bg-blue-400" style={{ width: pct(inspection.low_count) }} />
        )}
      </div>
      <span className="text-xs text-gray-500 whitespace-nowrap">{total} violations</span>
    </div>
  )
}

export default function Dashboard() {
  const [inspections, setInspections] = useState<Inspection[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const data = await inspectionsApi.list()
        setInspections(data)
      } finally {
        setLoading(false)
      }
    }
    load()

    // Poll every 5s so analyzing rows auto-update
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  // Summary stats
  const completed = inspections.filter(i => i.status === 'completed')
  const totalViolations = completed.reduce((s, i) => s + i.total_violations, 0)
  const criticals = completed.reduce((s, i) => s + i.critical_count, 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Inspections</h1>
          <p className="text-sm text-gray-500 mt-0.5">AI-powered OSHA safety inspection reports</p>
        </div>
        <Link to="/inspect" className="btn-primary">
          <PlusCircle className="w-4 h-4" />
          New Inspection
        </Link>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Total Inspections', value: inspections.length, color: 'text-gray-900' },
          { label: 'Total Violations', value: totalViolations, color: 'text-orange-600' },
          { label: 'Critical Issues', value: criticals, color: 'text-red-600' },
          {
            label: 'In Progress',
            value: inspections.filter(i => i.status === 'analyzing' || i.status === 'uploading').length,
            color: 'text-blue-600',
          },
        ].map(stat => (
          <div key={stat.label} className="card p-4">
            <p className="text-xs text-gray-500 font-medium">{stat.label}</p>
            <p className={clsx('text-3xl font-bold mt-1', stat.color)}>{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-gray-500">
        {[
          { color: 'bg-red-500', label: 'Critical' },
          { color: 'bg-orange-500', label: 'High' },
          { color: 'bg-yellow-400', label: 'Medium' },
          { color: 'bg-blue-400', label: 'Low' },
        ].map(item => (
          <span key={item.label} className="flex items-center gap-1.5">
            <span className={clsx('w-2.5 h-2.5 rounded-full', item.color)} />
            {item.label}
          </span>
        ))}
      </div>

      {/* Inspection list */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        </div>
      ) : inspections.length === 0 ? (
        <div className="card p-12 text-center">
          <AlertTriangle className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 font-medium">No inspections yet</p>
          <p className="text-sm text-gray-400 mt-1">
            Upload site photos to run your first AI safety inspection.
          </p>
          <Link to="/inspect" className="btn-primary mt-4 inline-flex">
            <PlusCircle className="w-4 h-4" />
            Start first inspection
          </Link>
        </div>
      ) : (
        <div className="card divide-y divide-gray-100 overflow-hidden">
          {inspections.map(inspection => (
            <Link
              key={inspection.id}
              to={`/inspection/${inspection.id}`}
              className="flex items-center gap-4 p-4 hover:bg-gray-50 transition-colors group"
            >
              <div className="flex-1 min-w-0 space-y-1.5">
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-gray-900 truncate">{inspection.site_name}</p>
                  <span
                    className={clsx(
                      'inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full',
                      STATUS_STYLES[inspection.status]
                    )}
                  >
                    {STATUS_ICONS[inspection.status]}
                    {inspection.status}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  {inspection.inspector_name && <span>{inspection.inspector_name}</span>}
                  {inspection.location && <span>{inspection.location}</span>}
                  <span>{format(new Date(inspection.created_at), 'MMM d, yyyy h:mm a')}</span>
                </div>
                {inspection.status === 'completed' && (
                  <SeverityBar inspection={inspection} />
                )}
              </div>
              <ChevronRight className="w-4 h-4 text-gray-300 group-hover:text-gray-500 flex-shrink-0 transition-colors" />
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
