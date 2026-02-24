import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, X, Image, Video } from 'lucide-react'
import clsx from 'clsx'

interface Props {
  files: File[]
  onChange: (files: File[]) => void
}

const ACCEPT = {
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/webp': ['.webp'],
  'video/mp4': ['.mp4'],
  'video/quicktime': ['.mov'],
}

export default function UploadZone({ files, onChange }: Props) {
  const onDrop = useCallback(
    (accepted: File[]) => onChange([...files, ...accepted]),
    [files, onChange]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT,
    multiple: true,
  })

  const remove = (idx: number) => onChange(files.filter((_, i) => i !== idx))

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={clsx(
          'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
          isDragActive
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-200 bg-gray-50 hover:border-blue-400 hover:bg-blue-50/50'
        )}
      >
        <input {...getInputProps()} />
        <Upload className="w-10 h-10 text-gray-400 mx-auto mb-3" />
        <p className="text-gray-700 font-medium">
          {isDragActive ? 'Drop files here' : 'Drag & drop photos or video'}
        </p>
        <p className="text-sm text-gray-400 mt-1">or click to browse — JPG, PNG, WebP, MP4, MOV</p>
      </div>

      {files.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {files.map((file, idx) => {
            const isImage = file.type.startsWith('image/')
            const url = URL.createObjectURL(file)
            return (
              <div key={idx} className="relative group rounded-lg overflow-hidden border border-gray-200 bg-gray-100 aspect-square">
                {isImage ? (
                  <img src={url} alt="" className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center gap-2">
                    <Video className="w-8 h-8 text-gray-400" />
                    <span className="text-xs text-gray-500 px-2 text-center truncate w-full">
                      {file.name}
                    </span>
                  </div>
                )}
                <button
                  onClick={() => remove(idx)}
                  className="absolute top-1 right-1 w-6 h-6 bg-red-500 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X className="w-3.5 h-3.5 text-white" />
                </button>
                <div className="absolute bottom-1 left-1">
                  {isImage
                    ? <Image className="w-3.5 h-3.5 text-white drop-shadow" />
                    : <Video className="w-3.5 h-3.5 text-white drop-shadow" />}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
