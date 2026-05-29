'use client'

import { cn } from '@/lib/utils'
import type { ClaimStatus } from '@/lib/types'

const statusConfig: Record<ClaimStatus, { label: string; classes: string }> = {
  APPROVED:      { label: 'Approved',      classes: 'bg-green-100 text-green-800 border-green-200' },
  PARTIAL:       { label: 'Partial',       classes: 'bg-amber-100 text-amber-800 border-amber-200' },
  REJECTED:      { label: 'Rejected',      classes: 'bg-red-100 text-red-800 border-red-200' },
  MANUAL_REVIEW: { label: 'Manual Review', classes: 'bg-blue-100 text-blue-800 border-blue-200' },
  PROCESSING:    { label: 'Processing',    classes: 'bg-gray-100 text-gray-600 border-gray-200' },
  ERROR:         { label: 'Error',         classes: 'bg-red-200 text-red-900 border-red-300' },
  PENDING:       { label: 'Pending',       classes: 'bg-gray-100 text-gray-500 border-gray-200' },
}

interface Props {
  status: ClaimStatus
  className?: string
}

export function ClaimStatusBadge({ status, className }: Props) {
  const config = statusConfig[status] ?? { label: status, classes: 'bg-gray-100 text-gray-600 border-gray-200' }
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium',
        config.classes,
        className
      )}
    >
      {status === 'PROCESSING' && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-gray-400" />
      )}
      {config.label}
    </span>
  )
}
