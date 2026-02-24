import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, Loader2, AlertTriangle, CheckCircle, Shield, FileText,
  Clock, TrendingUp, Calendar, User, MapPin,
} from 'lucide-react'
import { format } from 'date-fns'
import clsx from 'clsx'
import { inspectionsApi } from '../api/client'
import type { InspectionDetail as IDetail, Violation, Severity } from '../types'
import ViolationCard from '../components/ViolationCard'

const SEVERITY_ORDER: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }

function RiskGauge({ score }: { score: number }) {
  const color = score >= 75 ? '#dc2626' : score >= 50 ? '#ea580c' : score >= 25 ? '#ca8a04' : '#16a34a'
  return (
    <div className="flex flex-col items-center gap-1">
      <svg viewBox="0 0 100 60" className="w-32">
        <path d="M10,50 A40,40 0 0,1 90,50" fill="none" stroke="#e5e7eb" strokeWidth="10" strokeLinecap="round" />
        <path
          d="M10,50 A40,40 0 0,1 90,50"
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${score * 1.257} 200`}
        />
        <text x="50" y="52" textAnchor="middle" className="text-2xl font-bold" style={{ fontSize: 18, fill: color, fontWeight: 700 }}>
          {score}
        </text>
      </svg>
      <span className="text-xs text-gray-500">Risk Score</span>
    </div>
  )
}

function ReportSection({ report }: { report: NonNullable<IDetail['report']> }) {
  const compliance_color = report.compliance_status === 'COMPLIANT' ? 'text-green-600' : 'text-red-600'

  return (
    <div className="card p-6 space-y-6">
      <div className="flex items-start gap-4">
        <RiskGauge score={report.risk_score} />
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <Shield className="w-4 h-4 text-gray-400" />
            <span className="text-sm font-medium text-gray-700">Compliance Status</span>
            <span className={clsx('text-sm font-bold', compliance_color)}>{report.compliance_status}</span>
          </div>
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="w-4 h-4 text-gray-400" />
            <span className="text-sm text-gray-500">Estimated fine exposure:</span>
            <span className="text-sm font-semibold text-red-600">{report.estimated_fine_exposure}</span>
          </div>
          {report.follow_up_inspection_recommended && (
            <div className="inline-flex items-center gap-1.5 text-xs bg-orange-50 text-orange-700 border border-orange-200 rounded-full px-3 py-1">
              <AlertTriangle className="w-3 h-3" />
              Follow-up inspection recommended
            </div>
          )}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Executive Summary</h3>
        <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">{report.executive_summary}</p>
      </div>

      {report.immediate_actions.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-red-600 mb-2 flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4" /> Immediate Actions (Today)
          </h3>
          <ul className="space-y-1">
            {report.immediate_actions.map((a, i) => (
              <li key={i} className="text-sm text-gray-700 flex gap-2">
                <span className="text-red-500 font-bold flex-shrink-0">{i + 1}.</span>
                {a}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.short_term_actions.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-orange-600 mb-2 flex items-center gap-1.5">
            <Clock className="w-4 h-4" /> Short-term Actions (7 days)
          </h3>
          <ul className="space-y-1">
            {report.short_term_actions.map((a, i) => (
              <li key={i} className="text-sm text-gray-700 flex gap-2">
                <span className="text-orange-500 font-bold flex-shrink-0">{i + 1}.</span>
                {a}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.long_term_actions.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-blue-600 mb-2 flex items-center gap-1.5">
            <FileText className="w-4 h-4" /> Long-term Actions (30 days)
          </h3>
          <ul className="space-y-1">
            {report.long_term_actions.map((a, i) => (
              <li key={i} className="text-sm text-gray-700 flex gap-2">
                <span className="text-blue-500 font-bold flex-shrink-0">{i + 1}.</span>
                {a}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

type TabId = 'violations' | 'report'

export default function InspectionDetail() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<IDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<TabId>('violations')
  const [filter, setFilter] = useState<Severity | 'ALL'>('ALL')

  const load = async () => {
    if (!id) return
    try {
      const d = await inspectionsApi.get(id)
      setData(d)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const interval = setInterval(() => {
      if (data?.status === 'analyzing' || data?.status === 'uploading') load()
    }, 3000)
    return () => clearInterval(interval)
  }, [id, data?.status])

  const handleViolationUpdate = (updated: Violation) => {
    setData(prev =>
      prev
        ? {
            ...prev,
            violations: prev.violations.map(v => (v.id === updated.id ? updated : v)),
          }
        : prev
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  if (!data) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-500">Inspection not found.</p>
        <Link to="/dashboard" className="btn-primary mt-4 inline-flex">Back to dashboard</Link>
      </div>
    )
  }

  const isAnalyzing = data.status === 'analyzing' || data.status === 'uploading'

  const filteredViolations = (
    filter === 'ALL'
      ? [...data.violations]
      : data.violations.filter(v => v.severity === filter)
  ).sort((a, b) =>
    SEVERITY_ORDER[a.severity ?? 'LOW'] - SEVERITY_ORDER[b.severity ?? 'LOW']
  )

  const counts: Record<Severity, number> = {
    CRITICAL: data.critical_count,
    HIGH: data.high_count,
    MEDIUM: data.medium_count,
    LOW: data.low_count,
  }

  return (
    <div className="space-y-6">
      {/* Back + header */}
      <div>
        <Link to="/dashboard" className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 mb-3 transition-colors">
          <ArrowLeft className="w-4 h-4" />
          All inspections
        </Link>
        <div className="flex flex-wrap items-start gap-3 justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{data.site_name}</h1>
            <div className="flex flex-wrap items-center gap-3 mt-1 text-sm text-gray-500">
              {data.inspector_name && (
                <span className="flex items-center gap-1"><User className="w-3.5 h-3.5" />{data.inspector_name}</span>
              )}
              {data.location && (
                <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" />{data.location}</span>
              )}
              <span className="flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5" />
                {format(new Date(data.created_at), 'MMM d, yyyy h:mm a')}
              </span>
            </div>
          </div>

          {/* Status badge */}
          <span className={clsx(
            'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium',
            data.status === 'completed' ? 'bg-green-100 text-green-700' :
            data.status === 'failed' ? 'bg-red-100 text-red-700' :
            'bg-yellow-100 text-yellow-700 analyzing-pulse'
          )}>
            {isAnalyzing && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {data.status === 'completed' && <CheckCircle className="w-3.5 h-3.5" />}
            {data.status === 'failed' && <AlertTriangle className="w-3.5 h-3.5" />}
            {isAnalyzing ? 'Analyzing with Nova AI…' : data.status}
          </span>
        </div>
      </div>

      {/* Severity summary chips */}
      {data.status === 'completed' && (
        <div className="flex flex-wrap gap-2">
          {(
            [
              { key: 'CRITICAL', color: 'bg-red-500',    label: 'Critical' },
              { key: 'HIGH',     color: 'bg-orange-500', label: 'High' },
              { key: 'MEDIUM',   color: 'bg-yellow-400', label: 'Medium' },
              { key: 'LOW',      color: 'bg-blue-400',   label: 'Low' },
            ] as const
          ).map(({ key, color, label }) => (
            <div key={key} className="flex items-center gap-1.5 bg-white border border-gray-200 rounded-full px-3 py-1">
              <span className={clsx('w-2.5 h-2.5 rounded-full', color)} />
              <span className="text-sm text-gray-700 font-medium">{counts[key]}</span>
              <span className="text-xs text-gray-400">{label}</span>
            </div>
          ))}
          <div className="flex items-center gap-1.5 bg-gray-900 rounded-full px-3 py-1">
            <span className="text-sm text-white font-semibold">{data.total_violations}</span>
            <span className="text-xs text-gray-300">Total</span>
          </div>
        </div>
      )}

      {/* Analyzing state */}
      {isAnalyzing && (
        <div className="card p-8 text-center space-y-3">
          <Loader2 className="w-10 h-10 text-blue-500 animate-spin mx-auto" />
          <p className="font-semibold text-gray-900">AI Analysis in Progress</p>
          <div className="text-sm text-gray-500 space-y-1">
            <p>Step 1 — Nova Pro scanning photos for violations…</p>
            <p>Step 2 — Nova Lite mapping to OSHA regulations…</p>
            <p>Step 3 — Generating compliance report…</p>
          </div>
          <p className="text-xs text-gray-400">This takes 30–90 seconds. Page auto-updates.</p>
        </div>
      )}

      {/* Tabs */}
      {data.status === 'completed' && (
        <>
          <div className="flex gap-1 border-b border-gray-200">
            {([
              { id: 'violations', label: `Violations (${data.total_violations})` },
              { id: 'report',     label: 'Full Report' },
            ] as { id: TabId; label: string }[]).map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  'px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
                  tab === t.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'violations' && (
            <div className="space-y-4">
              {/* Filter */}
              <div className="flex flex-wrap gap-2">
                {(['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map(f => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={clsx(
                      'px-3 py-1 rounded-full text-xs font-medium transition-colors',
                      filter === f
                        ? 'bg-gray-900 text-white'
                        : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
                    )}
                  >
                    {f === 'ALL' ? `All (${data.total_violations})` : `${f} (${counts[f]})`}
                  </button>
                ))}
              </div>

              {filteredViolations.length === 0 ? (
                <div className="card p-8 text-center">
                  <CheckCircle className="w-10 h-10 text-green-400 mx-auto mb-2" />
                  <p className="text-gray-500">No violations in this category.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredViolations.map(v => (
                    <ViolationCard key={v.id} violation={v} onUpdate={handleViolationUpdate} />
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === 'report' && data.report && <ReportSection report={data.report} />}

          {tab === 'report' && !data.report && (
            <div className="card p-8 text-center">
              <p className="text-gray-500">Report not available yet.</p>
            </div>
          )}
        </>
      )}

      {data.status === 'failed' && (
        <div className="card p-6 border-red-200 bg-red-50 text-center">
          <AlertTriangle className="w-10 h-10 text-red-400 mx-auto mb-2" />
          <p className="font-semibold text-red-700">Analysis failed</p>
          <p className="text-sm text-red-500 mt-1">
            Check that AWS credentials are configured and Nova models are enabled in Bedrock.
          </p>
        </div>
      )}
    </div>
  )
}
