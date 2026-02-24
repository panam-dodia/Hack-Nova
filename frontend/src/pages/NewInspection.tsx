import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { HardHat, Loader2, ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import UploadZone from '../components/UploadZone'
import { inspectionsApi } from '../api/client'

export default function NewInspection() {
  const navigate = useNavigate()
  const [siteName, setSiteName] = useState('')
  const [inspector, setInspector] = useState('')
  const [location, setLocation] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!siteName.trim()) { setError('Site name is required'); return }
    if (files.length === 0) { setError('Upload at least one photo'); return }

    setError('')
    setSubmitting(true)

    try {
      const fd = new FormData()
      fd.append('site_name', siteName.trim())
      fd.append('inspector_name', inspector.trim())
      fd.append('location', location.trim())
      files.forEach(f => fd.append('files', f))

      const inspection = await inspectionsApi.create(fd)
      navigate(`/inspection/${inspection.id}`)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Upload failed. Check that the backend is running.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Back */}
      <Link to="/dashboard" className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back to dashboard
      </Link>

      <div>
        <h1 className="text-2xl font-bold text-gray-900">New Inspection</h1>
        <p className="text-sm text-gray-500 mt-1">
          Upload site photos and Nova AI will automatically detect OSHA violations.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card p-6 space-y-5">
        {/* Site info */}
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Site Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={siteName}
              onChange={e => setSiteName(e.target.value)}
              placeholder="e.g. Downtown Tower — Level 4"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Inspector Name
            </label>
            <input
              type="text"
              value={inspector}
              onChange={e => setInspector(e.target.value)}
              placeholder="e.g. John Doe"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            Location / Address
          </label>
          <input
            type="text"
            value={location}
            onChange={e => setLocation(e.target.value)}
            placeholder="e.g. 123 Main St, Chicago IL"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
          />
        </div>

        {/* Upload */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            Photos / Video <span className="text-red-500">*</span>
          </label>
          <UploadZone files={files} onChange={setFiles} />
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        {/* How it works */}
        <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 space-y-2">
          <p className="text-sm font-semibold text-blue-800 flex items-center gap-2">
            <HardHat className="w-4 h-4" />
            What happens after upload
          </p>
          <ol className="text-sm text-blue-700 space-y-1 list-decimal list-inside">
            <li>Nova Pro scans every photo for safety violations</li>
            <li>Nova Lite maps each finding to the exact OSHA regulation</li>
            <li>A full compliance report is generated automatically</li>
          </ol>
          <p className="text-xs text-blue-600">Analysis takes 30–90 seconds depending on the number of images.</p>
        </div>

        <button
          type="submit"
          disabled={submitting || files.length === 0 || !siteName.trim()}
          className="btn-primary w-full justify-center py-2.5"
        >
          {submitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Uploading & starting analysis…
            </>
          ) : (
            <>
              <HardHat className="w-4 h-4" />
              Run AI Inspection ({files.length} {files.length === 1 ? 'file' : 'files'})
            </>
          )}
        </button>
      </form>
    </div>
  )
}
