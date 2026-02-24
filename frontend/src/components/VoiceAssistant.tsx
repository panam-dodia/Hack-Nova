/**
 * VoiceAssistant — Real-time voice interface powered by Amazon Nova 2 Sonic.
 *
 * Audio pipeline (Nova Sonic mode):
 *   Mic → AudioContext → ScriptProcessor → downsample to 16kHz → Int16 PCM
 *   → binary WebSocket frames → backend → Nova 2 Sonic (Bedrock)
 *   → base64 PCM 24kHz → decode → AudioContext → speaker
 *
 * Fallback (text mode):
 *   Text input → POST /api/voice/chat → Nova Lite → text response + browser TTS
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { Mic, MicOff, X, Volume2, AlertCircle, Loader2, Radio } from 'lucide-react'
import clsx from 'clsx'
import type { Severity } from '../types'

interface Props {
  onClose: () => void
}

interface Message {
  role: 'inspector' | 'ai'
  text: string
  severity?: Severity | null
  osha_code?: string | null
}

const SEVERITY_STYLES: Record<Severity, string> = {
  CRITICAL: 'text-red-700 bg-red-50 border-red-200',
  HIGH:     'text-orange-700 bg-orange-50 border-orange-200',
  MEDIUM:   'text-yellow-700 bg-yellow-50 border-yellow-200',
  LOW:      'text-blue-700 bg-blue-50 border-blue-200',
}

const TARGET_SR = 16000  // Hz — what Nova Sonic expects as input
const CHUNK_SZ  = 4096   // ScriptProcessor buffer size

// ── Audio utilities ───────────────────────────────────────────────────────────

function downsample(buf: Float32Array, fromSR: number, toSR: number): Float32Array {
  if (fromSR === toSR) return buf
  const ratio = fromSR / toSR
  const out   = new Float32Array(Math.round(buf.length / ratio))
  for (let i = 0; i < out.length; i++) out[i] = buf[Math.round(i * ratio)]
  return out
}

function toInt16(buf: Float32Array): Int16Array {
  const out = new Int16Array(buf.length)
  for (let i = 0; i < buf.length; i++) {
    const s = Math.max(-1, Math.min(1, buf[i]))
    out[i]  = s < 0 ? s * 0x8000 : s * 0x7FFF
  }
  return out
}

async function playPCMBase64(
  b64: string,
  ctx: AudioContext,
  nextAt: React.MutableRefObject<number>
) {
  const bin   = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)

  const i16   = new Int16Array(bytes.buffer)
  const f32   = new Float32Array(i16.length)
  for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768

  const ab  = ctx.createBuffer(1, f32.length, 24000)
  ab.copyToChannel(f32, 0)
  const src = ctx.createBufferSource()
  src.buffer = ab
  src.connect(ctx.destination)
  const t = Math.max(ctx.currentTime, nextAt.current)
  src.start(t)
  nextAt.current = t + ab.duration
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function VoiceAssistant({ onClose }: Props) {
  const [messages,    setMessages]    = useState<Message[]>([{
    role: 'ai',
    text: 'SafetyAI ready — powered by Amazon Nova 2 Sonic. Hold the mic button and describe what you see.',
  }])
  const [recording,   setRecording]   = useState(false)
  const [status,      setStatus]      = useState<'idle'|'connecting'|'processing'|'speaking'>('idle')
  const [error,       setError]       = useState('')
  const [textMode,    setTextMode]    = useState(false)
  const [inputText,   setInputText]   = useState('')

  const scrollRef    = useRef<HTMLDivElement>(null)
  const wsRef        = useRef<WebSocket | null>(null)
  const audioCtxRef  = useRef<AudioContext | null>(null)
  const scriptRef    = useRef<ScriptProcessorNode | null>(null)
  const streamRef    = useRef<MediaStream | null>(null)
  const nextAt       = useRef(0)
  const pendingText  = useRef('')

  useEffect(() => { scrollRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])
  useEffect(() => () => {
    wsRef.current?.close()
    audioCtxRef.current?.close()
    streamRef.current?.getTracks().forEach(t => t.stop())
  }, [])

  // ── WebSocket ─────────────────────────────────────────────────────────────

  const connectWS = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws    = new WebSocket(`${proto}//${window.location.host}/ws/sonic`)
      wsRef.current = ws

      ws.onopen = () => resolve(ws)
      ws.onerror = () => {
        reject(new Error('WebSocket failed'))
        setTextMode(true)
      }

      ws.onmessage = (e) => {
        const msg: { type: string; content: string } = JSON.parse(e.data)

        if (msg.type === 'status') {
          if (msg.content === 'processing') setStatus('processing')
          if (msg.content === 'done') {
            setStatus('idle')
            if (pendingText.current.trim()) {
              const txt  = pendingText.current.trim()
              const sev  = extractSeverity(txt)
              const osha = extractOSHA(txt)
              setMessages(p => [...p, { role: 'ai', text: txt, severity: sev, osha_code: osha }])
              pendingText.current = ''
            }
          }
        } else if (msg.type === 'audio') {
          setStatus('speaking')
          if (audioCtxRef.current) playPCMBase64(msg.content, audioCtxRef.current, nextAt)
        } else if (msg.type === 'text') {
          pendingText.current += msg.content
        } else if (msg.type === 'error') {
          setError(msg.content)
          setStatus('idle')
        }
      }

      ws.onclose = () => { setStatus('idle'); setRecording(false) }
    })
  }, [])

  // ── Recording ────────────────────────────────────────────────────────────

  const startRecording = async () => {
    setError('')
    pendingText.current = ''
    try {
      if (!audioCtxRef.current || audioCtxRef.current.state === 'closed') {
        audioCtxRef.current = new AudioContext()
      }
      const ctx = audioCtxRef.current
      if (ctx.state === 'suspended') await ctx.resume()
      nextAt.current = 0

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
      streamRef.current = stream

      setStatus('connecting')
      const ws = await connectWS()

      const source  = ctx.createMediaStreamSource(stream)
      const script  = ctx.createScriptProcessor(CHUNK_SZ, 1, 1)
      scriptRef.current = script

      script.onaudioprocess = (ev) => {
        if (ws.readyState !== WebSocket.OPEN) return
        const raw  = ev.inputBuffer.getChannelData(0)
        const down = downsample(raw, ctx.sampleRate, TARGET_SR)
        ws.send(toInt16(down).buffer)
      }

      source.connect(script)
      script.connect(ctx.destination)

      setRecording(true)
      setStatus('processing')
      setMessages(p => [...p, { role: 'inspector', text: '🎙 Speaking…' }])

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Mic/WebSocket error: ${msg}`)
      setStatus('idle')
      setTextMode(true)
    }
  }

  const stopRecording = () => {
    setRecording(false)
    streamRef.current?.getTracks().forEach(t => t.stop())
    scriptRef.current?.disconnect()
    scriptRef.current = null
    setStatus('processing')

    // Replace the "Speaking…" placeholder with nothing — real transcript comes from Nova
    setMessages(p => p.filter(m => m.text !== '🎙 Speaking…'))

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send('end')
    }
  }

  // ── Text fallback ─────────────────────────────────────────────────────────

  const sendText = async () => {
    if (!inputText.trim()) return
    const text = inputText.trim()
    setInputText('')
    setMessages(p => [...p, { role: 'inspector', text }])
    setStatus('processing')
    try {
      const res  = await fetch('/api/voice/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      const data = await res.json()
      setMessages(p => [...p, {
        role: 'ai', text: data.spoken_response,
        severity: data.severity, osha_code: data.osha_code,
      }])
      if ('speechSynthesis' in window) {
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(data.spoken_response))
      }
    } catch { setError('Network error.') }
    finally   { setStatus('idle') }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  function extractSeverity(t: string): Severity | null {
    for (const s of ['CRITICAL','HIGH','MEDIUM','LOW'] as Severity[])
      if (t.toUpperCase().includes(s)) return s
    return null
  }
  function extractOSHA(t: string): string | null {
    return t.match(/(29\s*CFR\s*)?(1926|1910)\.\d+/i)?.[0] ?? null
  }

  const statusLabel = { idle:'Ready', connecting:'Connecting…', processing:'Thinking…', speaking:'Speaking…' }[status]

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg flex flex-col" style={{ maxHeight: '85vh' }}>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full flex items-center justify-center">
              <Radio className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="font-semibold text-gray-900 text-sm">SafetyAI Voice</p>
              <p className="text-xs text-gray-400">Amazon Nova 2 Sonic · real-time speech-to-speech</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium',
              status === 'idle'       && 'bg-gray-100 text-gray-500',
              status === 'connecting' && 'bg-yellow-100 text-yellow-700',
              status === 'processing' && 'bg-blue-100 text-blue-700',
              status === 'speaking'   && 'bg-green-100 text-green-700',
            )}>{statusLabel}</span>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.map((msg, i) => (
            <div key={i} className={clsx('flex', msg.role === 'inspector' ? 'justify-end' : 'justify-start')}>
              <div className={clsx('max-w-[88%] rounded-xl px-4 py-2.5 text-sm',
                msg.role === 'inspector'
                  ? 'bg-blue-600 text-white'
                  : msg.severity
                  ? clsx('border', SEVERITY_STYLES[msg.severity])
                  : 'bg-gray-100 text-gray-800'
              )}>
                {msg.severity && (
                  <div className="flex items-center gap-1.5 mb-1 text-xs font-bold uppercase tracking-wide">
                    <AlertCircle className="w-3.5 h-3.5" />
                    {msg.severity}
                    {msg.osha_code && <span className="font-mono opacity-70 ml-1">· {msg.osha_code}</span>}
                  </div>
                )}
                <p className="leading-relaxed">{msg.text}</p>
              </div>
            </div>
          ))}
          {status === 'processing' && (
            <div className="flex justify-start">
              <div className="bg-gray-100 rounded-xl px-4 py-2.5 flex items-center gap-2 text-sm text-gray-500">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />Nova Sonic processing…
              </div>
            </div>
          )}
          <div ref={scrollRef} />
        </div>

        {error && (
          <div className="px-4 py-2 bg-red-50 border-t border-red-100 text-xs text-red-600 flex gap-1.5">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />{error}
          </div>
        )}

        {/* Controls */}
        <div className="px-4 py-5 border-t border-gray-100">
          {!textMode ? (
            <div className="flex flex-col items-center gap-2">
              <button
                onMouseDown={startRecording}
                onMouseUp={stopRecording}
                onTouchStart={e => { e.preventDefault(); startRecording() }}
                onTouchEnd={e   => { e.preventDefault(); stopRecording() }}
                disabled={status === 'processing'}
                className={clsx(
                  'w-20 h-20 rounded-full flex items-center justify-center transition-all shadow-lg select-none',
                  recording
                    ? 'bg-red-500 scale-110 ring-4 ring-red-200'
                    : status === 'processing'
                    ? 'bg-gray-200 cursor-not-allowed'
                    : 'bg-gradient-to-br from-blue-500 to-indigo-600 hover:scale-105 active:scale-95'
                )}
              >
                {status === 'processing' && !recording
                  ? <Loader2 className="w-8 h-8 text-white animate-spin" />
                  : recording
                  ? <MicOff className="w-8 h-8 text-white" />
                  : <Mic className="w-8 h-8 text-white" />}
              </button>
              <p className="text-xs text-gray-400">{recording ? 'Release to send to Nova Sonic' : 'Hold to speak'}</p>
              <button onClick={() => setTextMode(true)} className="text-xs text-gray-400 underline hover:text-gray-600">
                Switch to text mode (Nova Lite)
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-xs text-gray-400 text-center">
                Text mode · Nova Lite ·{' '}
                <button onClick={() => setTextMode(false)} className="underline">try Nova Sonic voice</button>
              </p>
              <div className="flex gap-2">
                <input
                  autoFocus
                  type="text"
                  value={inputText}
                  onChange={e => setInputText(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && sendText()}
                  placeholder="Describe what you see on site…"
                  className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
                <button onClick={sendText} disabled={!inputText.trim() || status === 'processing'} className="btn-primary px-3">
                  {status === 'processing' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Volume2 className="w-4 h-4" />}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
