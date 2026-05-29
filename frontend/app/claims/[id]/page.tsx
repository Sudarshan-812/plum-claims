'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { ChevronLeft, Play, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { ClaimStatusBadge } from '@/components/claims/ClaimStatusBadge'
import { ClaimTypeIcon } from '@/components/claims/ClaimTypeIcon'
import { AuditTimeline } from '@/components/trace/AuditTimeline'
import { ReplayModal } from '@/components/trace/ReplayModal'
import { api, formatCurrency, formatDate, shortId } from '@/lib/api'
import { CLAIM_TYPE_LABELS, MEMBERS } from '@/lib/types'
import type { ClaimRecord, ClaimTrace, ReplayStep } from '@/lib/types'

function DetailSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-24 rounded-xl bg-gray-200" />
      <div className="h-40 rounded-xl bg-gray-200" />
      <div className="h-64 rounded-xl bg-gray-200" />
    </div>
  )
}

const decisionConfig: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  APPROVED:      { bg: 'bg-green-50',  border: 'border-green-200',  text: 'text-green-900',  icon: '✓' },
  PARTIAL:       { bg: 'bg-amber-50',  border: 'border-amber-200',  text: 'text-amber-900',  icon: '~' },
  REJECTED:      { bg: 'bg-red-50',    border: 'border-red-200',    text: 'text-red-900',    icon: '✗' },
  MANUAL_REVIEW: { bg: 'bg-blue-50',   border: 'border-blue-200',   text: 'text-blue-900',   icon: '⚑' },
}

export default function ClaimDetailPage() {
  const params  = useParams()
  const claimId = params?.id as string

  const [claim, setClaim]   = useState<ClaimRecord | null>(null)
  const [trace, setTrace]   = useState<ClaimTrace | null>(null)
  const [replay, setReplay] = useState<ReplayStep[] | null>(null)
  const [replayOpen, setReplayOpen]   = useState(false)
  const [replayIndex, setReplayIndex] = useState(0)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [reprocessing, setReprocessing] = useState(false)

  async function loadClaim() {
    try {
      const { claim: c, trace: t } = await api.getClaim(claimId)
      setClaim(c)
      setTrace(t)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load claim')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadClaim() }, [claimId])

  // Auto-refresh if still processing
  useEffect(() => {
    if (!claim || (claim.status !== 'PROCESSING' && claim.status !== 'PENDING')) return
    const id = setInterval(loadClaim, 3000)
    return () => clearInterval(id)
  }, [claim])

  async function openReplay() {
    if (!replay) {
      try {
        const { steps } = await api.getReplay(claimId)
        setReplay(steps)
        setReplayIndex(0)
        setReplayOpen(true)
      } catch {
        // Fall back to trace steps if replay endpoint fails
        setReplayOpen(true)
      }
    } else {
      setReplayIndex(0)
      setReplayOpen(true)
    }
  }

  async function handleReprocess() {
    setReprocessing(true)
    try {
      await api.reprocess(claimId)
      setTimeout(loadClaim, 500)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reprocess failed')
    } finally {
      setReprocessing(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
          <DetailSkeleton />
        </div>
      </div>
    )
  }

  if (error || !claim) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-500">{error || 'Claim not found'}</p>
          <Link href="/">
            <Button variant="outline" className="mt-3">Back to Dashboard</Button>
          </Link>
        </div>
      </div>
    )
  }

  const memberName = MEMBERS.find(m => m.id === claim.member_id)?.name ?? claim.member_id
  const dc = decisionConfig[claim.decision ?? ''] ?? decisionConfig['MANUAL_REVIEW']

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-4xl px-4 py-5 sm:px-6">
          <Link href="/" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
            <ChevronLeft className="h-4 w-4" /> Back to Dashboard
          </Link>

          <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold text-gray-900">
                  Claim {shortId(claim.claim_id)}
                </h1>
                <ClaimStatusBadge status={claim.status} />
              </div>
              <p className="mt-1 text-sm text-gray-500">
                {memberName} ({claim.member_id}) ·{' '}
                <ClaimTypeIcon type={claim.claim_type} />{' '}
                {CLAIM_TYPE_LABELS[claim.claim_type]} ·{' '}
                {formatDate(claim.created_at)}
              </p>
            </div>

            <div className="flex gap-2">
              {trace && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={openReplay}
                  className="gap-1.5 text-violet-600 border-violet-200 hover:bg-violet-50"
                >
                  <Play className="h-3.5 w-3.5" /> Replay
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={handleReprocess}
                disabled={reprocessing}
                className="gap-1.5"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${reprocessing ? 'animate-spin' : ''}`} />
                Reprocess
              </Button>
            </div>
          </div>

          {/* Amount strip */}
          <div className="mt-4 flex flex-wrap gap-6 text-sm">
            <div>
              <p className="text-gray-500">Claimed</p>
              <p className="font-mono font-semibold text-gray-900">{formatCurrency(claim.claimed_amount)}</p>
            </div>
            {claim.approved_amount != null && (
              <div>
                <p className="text-gray-500">Approved</p>
                <p className="font-mono font-semibold text-green-700">{formatCurrency(claim.approved_amount)}</p>
              </div>
            )}
            {claim.confidence_score != null && (
              <div>
                <p className="text-gray-500">Confidence</p>
                <div className="flex items-center gap-2">
                  <Progress value={claim.confidence_score * 100} className="h-2 w-20" />
                  <span className="font-mono font-semibold text-gray-900">
                    {Math.round(claim.confidence_score * 100)}%
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 sm:px-6">
        {/* Decision card */}
        {claim.decision && (
          <Card className={`border ${dc.border} ${dc.bg} shadow-none`}>
            <CardContent className="px-6 py-5">
              <div className="flex items-start gap-4">
                <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 ${dc.border} text-lg font-bold ${dc.text}`}>
                  {dc.icon}
                </div>
                <div className="flex-1">
                  <p className={`text-lg font-bold ${dc.text}`}>{claim.decision}</p>
                  {claim.approved_amount != null && claim.approved_amount > 0 && (
                    <p className={`mt-0.5 font-mono font-semibold ${dc.text}`}>
                      Approved: {formatCurrency(claim.approved_amount)}
                    </p>
                  )}
                  {claim.decision_reason && (
                    <p className={`mt-2 text-sm leading-relaxed ${dc.text} opacity-80`}>
                      {claim.decision_reason}
                    </p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Claim details */}
        <Card className="border border-gray-200 bg-white shadow-none">
          <CardContent className="p-6">
            <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Claim Details
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              {[
                ['Claim ID',        <span key="id" className="font-mono text-xs">{claim.claim_id}</span>],
                ['Member',          `${memberName} (${claim.member_id})`],
                ['Claim Type',      CLAIM_TYPE_LABELS[claim.claim_type]],
                ['Treatment Date',  claim.treatment_date],
                ['Submitted',       formatDate(claim.created_at)],
                ['Last Updated',    formatDate(claim.updated_at)],
              ].map(([label, value]) => (
                <div key={String(label)}>
                  <p className="text-xs text-gray-500">{label}</p>
                  <p className="mt-0.5 text-sm font-medium text-gray-900">{value}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Audit timeline */}
        {trace ? (
          <Card className="border border-gray-200 bg-white shadow-none">
            <CardContent className="p-6">
              <AuditTimeline trace={trace} />
            </CardContent>
          </Card>
        ) : (
          <Card className="border border-dashed border-gray-300 bg-white shadow-none">
            <CardContent className="py-10 text-center text-sm text-gray-500">
              {claim.status === 'PROCESSING' || claim.status === 'PENDING'
                ? 'Processing… trace will appear shortly'
                : 'No audit trace available for this claim'}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Replay modal */}
      {replayOpen && (replay ?? []).length > 0 && (
        <ReplayModal
          steps={replay!}
          currentIndex={replayIndex}
          onClose={() => setReplayOpen(false)}
          onPrev={() => setReplayIndex(i => Math.max(0, i - 1))}
          onNext={() => setReplayIndex(i => Math.min((replay!).length - 1, i + 1))}
        />
      )}
    </div>
  )
}
