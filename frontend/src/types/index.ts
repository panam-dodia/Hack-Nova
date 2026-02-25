export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
export type InspectionStatus = 'pending' | 'uploading' | 'analyzing' | 'completed' | 'failed'
export type ViolationStatus = 'open' | 'in_progress' | 'resolved'

export interface Violation {
  id: string
  inspection_id: string
  image_index: number | null
  raw_observation: string | null
  hazard_type: string | null
  location_in_image: string | null
  osha_code: string | null
  osha_title: string | null
  severity: Severity | null
  plain_english: string | null
  remediation: string | null
  estimated_fix_time: string | null
  status: ViolationStatus
  ticket_id: string | null
  ticket_url: string | null
  assigned_to: string | null
}

export interface Inspection {
  id: string
  site_name: string
  location: string | null
  inspector_name: string | null
  status: InspectionStatus
  created_at: string
  total_violations: number
  critical_count: number
  high_count: number
  medium_count: number
  low_count: number
}

export interface ReportData {
  executive_summary: string
  risk_score: number
  risk_level: string
  risk_rationale: string
  immediate_actions: string[]
  short_term_actions: string[]
  long_term_actions: string[]
  compliance_status: string
  estimated_fine_exposure: string
  follow_up_inspection_recommended: boolean
  notes: string
}

export interface InspectionDetail extends Inspection {
  violations: Violation[]
  report: ReportData | null
}

export interface VoiceChatResponse {
  spoken_response: string
  severity: Severity | null
  osha_code: string | null
  original_text: string
  is_violation: boolean
}

// Real-time monitoring types
export type MonitoringStatus = 'pending' | 'processing' | 'paused' | 'completed' | 'stopped' | 'failed'

export interface MonitoringSession {
  id: string
  video_file_path: string
  original_filename: string | null
  status: MonitoringStatus
  frame_rate: number | null
  total_frames: number | null
  duration_seconds: number | null
  current_frame: number
  current_timestamp: number
  violations_detected_count: number
  analysis_interval_seconds: number
  auto_ticket_filing: boolean
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface ViolationAlert {
  violation_id: string
  session_id: string
  timestamp: number
  frame_number: number
  hazard_type: string
  severity: Severity
  observation: string
  location: string
  osha_code: string | null
  osha_title: string | null
  plain_english: string | null
  frame_path: string | null
  video_clip_path: string | null
  detected_at: string
}
