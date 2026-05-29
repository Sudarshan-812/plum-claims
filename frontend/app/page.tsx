'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ClaimStats } from '@/components/claims/ClaimStats'
import { ClaimTable } from '@/components/claims/ClaimTable'
import { api } from '@/lib/api'
import type { ClaimRecord, ClaimStatus } from '@/lib/types'

const STATUS_FILTERS: { label: string; value: ClaimStatus | 'ALL' }[] = [
  { label: 'All',           value: 'ALL' },
  { label: 'Approved',      value: 'APPROVED' },
  { label: 'Partial',       value: 'PARTIAL' },
  { label: 'Rejected',      value: 'REJECTED' },
  { label: 'Manual Review', value: 'MANUAL_REVIEW' },
  { label: 'Processing',    value: 'PROCESSING' },
]

function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-2 rounded-lg border border-gray-200 bg-white p-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-10 rounded bg-gray-100" />
      ))}
    </div>
  )
}

export default function DashboardPage() {
  const [claims, setClaims]   = useState<ClaimRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [filter, setFilter]   = useState<ClaimStatus | 'ALL'>('ALL')

  const fetchClaims = useCallback(async () => {
    try {
      const data = await api.getClaims()
      setClaims(data)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load claims')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchClaims() }, [fetchClaims])

  // Auto-refresh while any claim is still processing
  useEffect(() => {
    const hasActive = claims.some(c => c.status === 'PROCESSING' || c.status === 'PENDING')
    if (!hasActive) return
    const id = setInterval(fetchClaims, 3000)
    return () => clearInterval(id)
  }, [claims, fetchClaims])

  const filtered = filter === 'ALL' ? claims : claims.filter(c => c.status === filter)

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-2xl">🌸</span>
                <h1 className="text-2xl font-bold text-gray-900">Plum Claims</h1>
              </div>
              <p className="mt-0.5 text-sm text-gray-500">
                AI-powered health insurance claims processing
              </p>
            </div>
            <Link href="/claims/new">
              <Button className="bg-violet-600 hover:bg-violet-700 text-white shadow-sm">
                + New Claim
              </Button>
            </Link>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            {error} —{' '}
            <button onClick={fetchClaims} className="underline hover:no-underline">
              Retry
            </button>
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5 animate-pulse">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-20 rounded-lg bg-gray-200" />
            ))}
          </div>
        ) : (
          <ClaimStats claims={claims} />
        )}

        <div className="flex items-center justify-between gap-4 flex-wrap">
          <Tabs value={filter} onValueChange={v => setFilter(v as ClaimStatus | 'ALL')}>
            <TabsList className="bg-white border border-gray-200">
              {STATUS_FILTERS.map(f => (
                <TabsTrigger
                  key={f.value}
                  value={f.value}
                  className="data-[state=active]:bg-violet-600 data-[state=active]:text-white text-sm"
                >
                  {f.label}
                  {f.value !== 'ALL' && (
                    <span className="ml-1.5 rounded-full bg-gray-100 px-1.5 text-xs text-gray-600">
                      {claims.filter(c =>
                        f.value === 'PROCESSING'
                          ? c.status === 'PROCESSING' || c.status === 'PENDING'
                          : c.status === f.value
                      ).length}
                    </span>
                  )}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <button
            onClick={fetchClaims}
            className="text-xs text-gray-400 hover:text-violet-600 transition"
          >
            ↻ Refresh
          </button>
        </div>

        {loading ? <TableSkeleton /> : <ClaimTable claims={filtered} />}
      </div>
    </div>
  )
}
