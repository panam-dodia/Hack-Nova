import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Video,
  Upload,
  Play,
  Pause,
  Square,
  AlertTriangle,
  CheckCircle,
  Clock,
  Loader2,
  Volume2,
  VolumeX,
  ArrowLeft
} from 'lucide-react'
import clsx from 'clsx'
import { monitoringApi } from '../api/client'
import type { MonitoringSession, ViolationAlert, Severity } from '../types'

const SEVERITY_STYLES: Record<Severity, string> = {
  CRITICAL: 'border-l-4 border-red-500 bg-red-50',
  HIGH: 'border-l-4 border-orange-500 bg-orange-50',
  MEDIUM: 'border-l-4 border-yellow-500 bg-yellow-50',
  LOW: 'border-l-4 border-blue-500 bg-blue-50',
}

const SEVERITY_ICONS: Record<Severity, React.ReactNode> = {
  CRITICAL: <AlertTriangle className="w-5 h-5 text-red-600" />,
  HIGH: <AlertTriangle className="w-5 h-5 text-orange-600" />,
  MEDIUM: <Clock className="w-5 h-5 text-yellow-600" />,
  LOW: <CheckCircle className="w-5 h-5 text-blue-600" />,
}

function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

export default function LiveMonitor() {
  const navigate = useNavigate()
  const [session, setSession] = useState<MonitoringSession | null>(null)
  const [violations, setViolations] = useState<ViolationAlert[]>([])
  const [uploading, setUploading] = useState(false)
  const [soundEnabled, setSoundEnabled] = useState(true)
  const wsRef = useRef<WebSocket | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  // Create audio element for alerts
  useEffect(() => {
    // Create alert sound (simple beep using Web Audio API)
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()

    const playAlertSound = () => {
      if (!soundEnabled) return

      const oscillator = audioContext.createOscillator()
      const gainNode = audioContext.createGain()

      oscillator.connect(gainNode)
      gainNode.connect(audioContext.destination)

      oscillator.frequency.value = 800
      oscillator.type = 'sine'

      gainNode.gain.setValueAtTime(0.3, audioContext.currentTime)
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5)

      oscillator.start(audioContext.currentTime)
      oscillator.stop(audioContext.currentTime + 0.5)
    }

    audioRef.current = { play: playAlertSound } as any

    return () => {
      audioContext.close()
    }
  }, [soundEnabled])

  // WebSocket connection
  useEffect(() => {
    if (!session) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.hostname}:8000/api/monitoring/ws/${session.id}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('WebSocket connected to monitoring session', session.id)
    }

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data)

      if (message.type === 'violation') {
        const alert: ViolationAlert = message.data
        setViolations(prev => [alert, ...prev])

        // Play alert sound
        if (audioRef.current && soundEnabled) {
          ;(audioRef.current as any).play()
        }

        // Show browser notification if permitted
        if (Notification.permission === 'granted') {
          new Notification('🚨 Safety Violation Detected', {
            body: `${alert.severity}: ${alert.hazard_type} - ${alert.observation.slice(0, 100)}`,
            icon: '/favicon.ico',
          })
        }
      } else if (message.type === 'progress') {
        setSession(prev => prev ? {
          ...prev,
          current_timestamp: message.data.current_time,
          current_frame: message.data.frame,
        } : null)
      } else if (message.type === 'completed') {
        setSession(prev => prev ? { ...prev, status: 'completed' } : null)
      } else if (message.type === 'error') {
        console.error('Monitoring error:', message.data.error)
        setSession(prev => prev ? { ...prev, status: 'failed' } : null)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
    }

    return () => {
      ws.close()
    }
  }, [session, soundEnabled])

  // Request notification permission on mount
  useEffect(() => {
    if (Notification.permission === 'default') {
      Notification.requestPermission()
    }
  }, [])

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const formData = new FormData()
    formData.append('video', file)
    formData.append('analysis_interval', '1.5')
    formData.append('auto_ticket_filing', 'true')

    setUploading(true)
    try {
      const newSession = await monitoringApi.create(formData)
      setSession(newSession)
      setViolations([])
    } catch (error) {
      console.error('Upload failed:', error)
      alert('Failed to start monitoring session')
    } finally {
      setUploading(false)
    }
  }

  const handlePause = async () => {
    if (!session) return
    await monitoringApi.pause(session.id)
    setSession({ ...session, status: 'paused' })
  }

  const handleResume = async () => {
    if (!session) return
    await monitoringApi.resume(session.id)
    setSession({ ...session, status: 'processing' })
  }

  const handleStop = async () => {
    if (!session) return
    await monitoringApi.stop(session.id)
    setSession({ ...session, status: 'stopped' })
  }

  const progressPercent = session && session.duration_seconds
    ? (session.current_timestamp / session.duration_seconds) * 100
    : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="p-2 hover:bg-gray-100 rounded-lg transition"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Video className="w-7 h-7 text-red-600" />
              Live Safety Monitor
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Real-time violation detection from video footage
            </p>
          </div>
        </div>

        <button
          onClick={() => setSoundEnabled(!soundEnabled)}
          className={clsx(
            'p-2.5 rounded-lg transition',
            soundEnabled ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-400'
          )}
        >
          {soundEnabled ? <Volume2 className="w-5 h-5" /> : <VolumeX className="w-5 h-5" />}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Upload & Controls */}
        <div className="lg:col-span-1 space-y-4">
          {/* Upload section */}
          {!session && (
            <div className="card p-6">
              <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <Upload className="w-5 h-5" />
                Upload Video
              </h2>
              <label className="block">
                <input
                  type="file"
                  accept="video/mp4,video/quicktime,video/avi"
                  onChange={handleUpload}
                  disabled={uploading}
                  className="hidden"
                  id="video-upload"
                />
                <label
                  htmlFor="video-upload"
                  className={clsx(
                    'btn-primary w-full justify-center cursor-pointer',
                    uploading && 'opacity-50 cursor-not-allowed'
                  )}
                >
                  {uploading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4" />
                      Select Video File
                    </>
                  )}
                </label>
              </label>
              <p className="text-xs text-gray-500 mt-3">
                Supported formats: MP4, MOV, AVI. The video will be analyzed frame-by-frame
                to detect safety violations in real-time.
              </p>
            </div>
          )}

          {/* Session info */}
          {session && (
            <div className="card p-6 space-y-4">
              <div>
                <h2 className="font-semibold text-gray-900 mb-2">Session Info</h2>
                <div className="text-sm space-y-1.5">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Status:</span>
                    <span className={clsx(
                      'font-medium',
                      session.status === 'processing' && 'text-blue-600',
                      session.status === 'completed' && 'text-green-600',
                      session.status === 'paused' && 'text-yellow-600',
                      session.status === 'failed' && 'text-red-600'
                    )}>
                      {session.status}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Duration:</span>
                    <span className="font-medium">
                      {session.duration_seconds ? formatTimestamp(session.duration_seconds) : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Frame Rate:</span>
                    <span className="font-medium">{session.frame_rate?.toFixed(1) ?? 'N/A'} fps</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Violations:</span>
                    <span className="font-bold text-red-600">{violations.length}</span>
                  </div>
                </div>
              </div>

              {/* Progress bar */}
              {session.status === 'processing' && (
                <div>
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>{formatTimestamp(session.current_timestamp)}</span>
                    <span>{session.duration_seconds ? formatTimestamp(session.duration_seconds) : '--:--'}</span>
                  </div>
                  <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-600 transition-all duration-300"
                      style={{ width: `${progressPercent}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Controls */}
              <div className="flex gap-2">
                {session.status === 'processing' && (
                  <button onClick={handlePause} className="btn-secondary flex-1 justify-center">
                    <Pause className="w-4 h-4" />
                    Pause
                  </button>
                )}
                {session.status === 'paused' && (
                  <button onClick={handleResume} className="btn-primary flex-1 justify-center">
                    <Play className="w-4 h-4" />
                    Resume
                  </button>
                )}
                {(session.status === 'processing' || session.status === 'paused') && (
                  <button onClick={handleStop} className="btn-danger flex-1 justify-center">
                    <Square className="w-4 h-4" />
                    Stop
                  </button>
                )}
                {(session.status === 'completed' || session.status === 'stopped') && (
                  <button
                    onClick={() => {
                      setSession(null)
                      setViolations([])
                    }}
                    className="btn-primary w-full justify-center"
                  >
                    <Upload className="w-4 h-4" />
                    New Session
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right: Live Violations Feed */}
        <div className="lg:col-span-2">
          <div className="card p-6">
            <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-600" />
              Live Violations ({violations.length})
            </h2>

            {violations.length === 0 && (
              <div className="text-center py-12 text-gray-400">
                <CheckCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p className="text-sm">No violations detected yet</p>
                {!session && <p className="text-xs mt-1">Upload a video to start monitoring</p>}
              </div>
            )}

            <div className="space-y-3 max-h-[600px] overflow-y-auto">
              {violations.map((violation, idx) => (
                <div
                  key={violation.violation_id}
                  className={clsx(
                    'p-4 rounded-lg',
                    SEVERITY_STYLES[violation.severity],
                    idx === 0 && 'animate-pulse-once'
                  )}
                >
                  <div className="flex items-start gap-3">
                    {SEVERITY_ICONS[violation.severity]}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <h3 className="font-semibold text-gray-900">
                          {violation.hazard_type}
                        </h3>
                        <span className="text-xs font-mono text-gray-500">
                          {formatTimestamp(violation.timestamp)}
                        </span>
                      </div>

                      <p className="text-sm text-gray-700 mb-2">
                        {violation.observation}
                      </p>

                      {violation.osha_code && (
                        <div className="text-xs bg-white bg-opacity-50 rounded px-2 py-1 inline-block mb-2">
                          <span className="font-semibold">{violation.osha_code}</span>
                          {violation.osha_title && (
                            <span className="text-gray-600 ml-1">— {violation.osha_title}</span>
                          )}
                        </div>
                      )}

                      {violation.plain_english && (
                        <p className="text-xs text-gray-600 italic mt-2">
                          {violation.plain_english}
                        </p>
                      )}

                      <div className="flex items-center gap-2 mt-3 text-xs text-gray-500">
                        <span>📍 {violation.location}</span>
                        <span>•</span>
                        <span>Frame {violation.frame_number}</span>
                        {violation.video_clip_path && (
                          <>
                            <span>•</span>
                            <span className="text-blue-600">📹 Clip saved</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Instructions */}
      {!session && (
        <div className="card p-6 bg-blue-50 border-blue-200">
          <h3 className="font-semibold text-blue-900 mb-2 flex items-center gap-2">
            <Video className="w-5 h-5" />
            How Real-Time Monitoring Works
          </h3>
          <ul className="text-sm text-blue-800 space-y-1.5 ml-5 list-disc">
            <li>Upload a video file (simulates live CCTV feed for the hackathon)</li>
            <li>Video is analyzed frame-by-frame every 1-2 seconds using Amazon Nova Pro</li>
            <li>Violations appear instantly with sound alerts and browser notifications</li>
            <li>30-second video clips are automatically saved as evidence</li>
            <li>Tickets are auto-filed via Nova Act for critical violations</li>
            <li>Duplicate violations are suppressed with 5-minute cooldown</li>
          </ul>
        </div>
      )}
    </div>
  )
}
