'use client'

import { useRef, useState } from 'react'
import { X, Upload } from 'lucide-react'
import type { ClaimType } from '@/lib/types'
import { REQUIRED_DOCS } from '@/lib/types'

interface Props {
  claimType: ClaimType
  files: File[]
  onChange: (files: File[]) => void
}

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB

export function DocumentUpload({ claimType, files, onChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState('')

  const requiredDocs = REQUIRED_DOCS[claimType] ?? []

  function addFiles(incoming: FileList | null) {
    if (!incoming) return
    const newFiles: File[] = []
    const errors: string[] = []

    Array.from(incoming).forEach(f => {
      if (f.size > MAX_FILE_SIZE) {
        errors.push(`${f.name} exceeds 10MB`)
        return
      }
      if (!['image/jpeg', 'image/png', 'image/webp', 'application/pdf'].includes(f.type)) {
        errors.push(`${f.name} is not JPG, PNG, or PDF`)
        return
      }
      newFiles.push(f)
    })

    if (errors.length) setError(errors.join(' · '))
    else setError('')

    onChange([...files, ...newFiles])
  }

  function removeFile(index: number) {
    onChange(files.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-3">
      {/* Required docs hint */}
      <div className="rounded-lg bg-violet-50 border border-violet-100 px-3 py-2 text-sm text-violet-700">
        <span className="font-medium">{claimType}</span> requires:{' '}
        {requiredDocs.join(', ')}
      </div>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) }}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-xl border-2 border-dashed py-10 text-center transition ${
          dragOver
            ? 'border-violet-400 bg-violet-50'
            : 'border-gray-300 bg-white hover:border-violet-300 hover:bg-gray-50'
        }`}
      >
        <Upload className="mx-auto h-8 w-8 text-gray-400" />
        <p className="mt-2 text-sm font-medium text-gray-700">
          Drop files here or <span className="text-violet-600">click to browse</span>
        </p>
        <p className="mt-1 text-xs text-gray-400">JPG, PNG, PDF · Max 10MB each</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".jpg,.jpeg,.png,.pdf,.webp"
          className="sr-only"
          onChange={e => addFiles(e.target.files)}
        />
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      {/* File chips */}
      {files.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {files.map((f, i) => (
            <div
              key={i}
              className="flex items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-700"
            >
              <span className="text-gray-400">
                {f.type === 'application/pdf' ? '📄' : '🖼️'}
              </span>
              <span className="max-w-[160px] truncate">{f.name}</span>
              <span className="text-xs text-gray-400">
                ({(f.size / 1024).toFixed(0)}KB)
              </span>
              <button
                type="button"
                onClick={() => removeFile(i)}
                className="ml-0.5 text-gray-400 hover:text-red-500"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
