import { useState } from 'react'
import { ChevronDown, ChevronUp, AlertTriangle, CheckCircle2, Clock, ExternalLink } from 'lucide-react'
import clsx from 'clsx'
import type { Violation, Severity } from '../types'
import { inspectionsApi } from '../api/client'

interface Props {
  violation: Violation
  onUpdate?: (updated: Violation) => void
}

const SEVERITY_STYLES: Record<Severity, { badge: string; border: string; bg: string }> = {
  CRITICAL: { badge: 'bg-red-100 text-red-700 ring-1 ring-red-300',   border: 'border-l-red-500',   bg: 'bg-red-50' },
  HIGH:     { badge: 'bg-orange-100 text-orange-700 ring-1 ring-orange-300', border: 'border-l-orange-500', bg: 'bg-orange-50' },
  MEDIUM:   { badge: 'bg-yellow-100 text-yellow-700 ring-1 ring-yellow-300', border: 'border-l-yellow-500', bg: 'bg-yellow-50' },
  LOW:      { badge: 'bg-blue-100 text-blue-700 ring-1 ring-blue-300',   border: 'border-l-blue-500',   bg: 'bg-blue-50' },
}

const STATUS_ICONS = {
  open:        <AlertTriangle className="w-4 h-4 text-red-500" />,
  in_progress: <Clock className="w-4 h-4 text-yellow-500" />,
  resolved:    <CheckCircle2 className="w-4 h-4 text-green-500" />,
}

export default function ViolationCard({ violation, onUpdate }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [saving, setSaving] = useState(false)
  const sev = violation.severity as Severity ?? 'LOW'
  const styles = SEVERITY_STYLES[sev]

  const handleStatusChange = async (newStatus: string) => {
    setSaving(true)
    try {
      const updated = await inspectionsApi.updateViolation(
        violation.inspection_id,
        violation.id,
        { status: newStatus as Violation['status'] }
      )
      onUpdate?.(updated)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={clsx('card border-l-4 overflow-hidden', styles.border)}>
      {/* Header row */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-start gap-3 p-4 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className={clsx('text-xs font-semibold px-2 py-0.5 rounded-full', styles.badge)}>
              {sev}
            </span>
            {violation.osha_code && (
              <span className="text-xs text-gray-500 font-mono bg-gray-100 px-2 py-0.5 rounded">
                {violation.osha_code}
              </span>
            )}
            {violation.osha_title && (
              <span className="text-xs text-gray-600 font-medium">{violation.osha_title}</span>
            )}
            <span className="ml-auto flex items-center gap-1 text-xs text-gray-500">
              {STATUS_ICONS[violation.status]}
              {violation.status.replace('_', ' ')}
            </span>
          </div>

          <p className="text-sm text-gray-800 font-medium leading-snug">
            {violation.plain_english ?? violation.raw_observation ?? 'Violation detected'}
          </p>
        </div>

        <div className="text-gray-400 flex-shrink-0 mt-0.5">
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-gray-100">
          {violation.raw_observation && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Raw observation
              </p>
              <p className="text-sm text-gray-600 italic">{violation.raw_observation}</p>
            </div>
          )}

          {violation.remediation && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Remediation steps
              </p>
              <p className="text-sm text-gray-700 whitespace-pre-line">{violation.remediation}</p>
            </div>
          )}

          <div className="flex flex-wrap gap-4 text-sm text-gray-600">
            {violation.estimated_fix_time && (
              <span>
                <span className="font-medium">Fix time:</span> {violation.estimated_fix_time}
              </span>
            )}
            {violation.hazard_type && (
              <span>
                <span className="font-medium">Category:</span> {violation.hazard_type}
              </span>
            )}
            {violation.location_in_image && (
              <span>
                <span className="font-medium">Location:</span> {violation.location_in_image}
              </span>
            )}
          </div>

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-2 pt-2">
            <select
              value={violation.status}
              onChange={e => handleStatusChange(e.target.value)}
              disabled={saving}
              className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:ring-2 focus:ring-blue-500 outline-none"
            >
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
            </select>

            {violation.ticket_url && (
              <a
                href={violation.ticket_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary text-xs"
              >
                <ExternalLink className="w-3 h-3" />
                View Ticket #{violation.ticket_id}
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
