'use client'

import { Card, CardContent } from '@/components/ui/card'
import type { ClaimRecord } from '@/lib/types'

interface Props {
  claims: ClaimRecord[]
}

export function ClaimStats({ claims }: Props) {
  const total        = claims.length
  const approved     = claims.filter(c => c.status === 'APPROVED').length
  const partial      = claims.filter(c => c.status === 'PARTIAL').length
  const rejected     = claims.filter(c => c.status === 'REJECTED').length
  const manualReview = claims.filter(c => c.status === 'MANUAL_REVIEW').length
  const processing   = claims.filter(c => c.status === 'PROCESSING' || c.status === 'PENDING').length

  const stats = [
    { label: 'Total Claims',   value: total,        color: 'text-gray-900' },
    { label: 'Approved',       value: approved + partial, color: 'text-green-600' },
    { label: 'Rejected',       value: rejected,     color: 'text-red-600'   },
    { label: 'Manual Review',  value: manualReview, color: 'text-blue-600'  },
    { label: 'Processing',     value: processing,   color: 'text-gray-500'  },
  ]

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {stats.map(s => (
        <Card key={s.label} className="border border-gray-200 bg-white shadow-none">
          <CardContent className="p-4">
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            <p className="mt-1 text-xs text-gray-500">{s.label}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
