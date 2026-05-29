'use client'

import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { api, shortId } from '@/lib/api'
import type { ReplayStep } from '@/lib/types'

const stepIcons: Record<string, string> = {
  DocumentVerificationAgent: '🔍',
  DocumentParsingAgent:      '📄',
  FraudDetectionAgent:       '🛡️',
  PolicyEvaluationAgent:     '📋',
  DecisionAgent:             '⚖️',
  AuditAgent:                '💾',
}

export default function ReplayPage() {
  const params  = useParams()
  const claimId = params?.id as string

  const [steps, setSteps]   = useState<ReplayStep[]>([])
  const [current, setCurrent] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState('')

  useEffect(() => {
    api.getReplay(claimId)
      .then(({ steps }) => setSteps(steps))
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load replay'))
      .finally(() => setLoading(false))
  }, [claimId])

  const prev = useCallback(() => setCurrent(i => Math.max(0, i - 1)), [])
  const next = useCallback(() => setCurrent(i => Math.min(steps.length - 1, i + 1)), [steps.length])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next()
      if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   prev()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, prev])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-900">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-violet-400 border-t-transparent" />
      </div>
    )
  }

  if (error || !steps.length) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-gray-900 text-white">
        <p>{error || 'No replay steps found'}</p>
        <Link href={`/claims/${claimId}`}>
          <Button variant="outline" className="text-white border-white hover:bg-white/10">
            Back to Claim
          </Button>
        </Link>
      </div>
    )
  }

  const step   = steps[current]
  const isLast = current === steps.length - 1
  const icon   = stepIcons[step.agent_name] ?? '📌'
  const output = step.full_data?.output as Record<string, unknown> | undefined

  return (
    <div className="flex min-h-screen flex-col bg-gray-900 text-white">
      {/* Nav bar */}
      <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <Link href={`/claims/${claimId}`} className="flex items-center gap-1 text-sm text-gray-400 hover:text-white">
          <X className="h-4 w-4" /> Close
        </Link>
        <p className="text-sm text-gray-400">
          Claim {shortId(claimId)} — Replay
        </p>
        <p className="text-sm font-medium text-violet-400">
          {current + 1} / {steps.length}
        </p>
      </div>

      {/* Main content */}
      <div className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-xl">
          {/* Step header */}
          <div className="mb-6 text-center">
            <div className="mb-2 text-4xl">{icon}</div>
            <p className="text-xs font-semibold uppercase tracking-widest text-violet-400">
              Step {current + 1} of {steps.length}
            </p>
            <h1 className="mt-1 text-2xl font-bold">{step.title}</h1>
            <p className="mt-1 text-sm text-gray-400">{step.description}</p>
          </div>

          {/* Step card */}
          <div className="rounded-2xl bg-white/5 border border-white/10 p-6 backdrop-blur">
            {/* Status */}
            <div className="mb-4 flex items-center justify-between">
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                step.status === 'SUCCESS' ? 'bg-green-900/50 text-green-300' :
                step.status === 'FAILED'  ? 'bg-red-900/50 text-red-300' :
                                            'bg-gray-700 text-gray-300'
              }`}>
                {step.status}
              </span>
              <span className="text-xs text-gray-500">{step.duration_ms}ms</span>
            </div>

            {/* Summaries */}
            <div className="space-y-3 text-sm">
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">Input</p>
                <p className="text-gray-300">{step.input_summary}</p>
              </div>
              <div className="border-t border-white/10 pt-3">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">Output</p>
                <p className="text-gray-300">{step.output_summary}</p>
              </div>
            </div>

            {/* Decision highlight */}
            {step.agent_name === 'DecisionAgent' && output && (
              <div className="mt-4 rounded-xl bg-violet-900/30 border border-violet-500/30 p-4 text-center">
                <p className="text-2xl font-bold text-violet-300">
                  {output.decision as string}
                </p>
                {typeof output.approved_amount === 'number' && output.approved_amount > 0 && (
                  <p className="mt-1 font-mono text-violet-200">
                    ₹{(output.approved_amount as number).toLocaleString('en-IN')}
                  </p>
                )}
                {typeof output.confidence_score === 'number' && (
                  <div className="mt-2 flex items-center justify-center gap-2">
                    <Progress value={(output.confidence_score as number) * 100} className="h-1.5 w-32 bg-violet-900" />
                    <span className="text-xs text-violet-400">
                      {Math.round((output.confidence_score as number) * 100)}%
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Navigation */}
          <div className="mt-6 flex items-center justify-between">
            <Button
              variant="outline"
              onClick={prev}
              disabled={current === 0}
              className="gap-1 border-white/20 text-white hover:bg-white/10 disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" /> Previous
            </Button>

            {/* Dots */}
            <div className="flex gap-1.5">
              {steps.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setCurrent(i)}
                  className={`h-2 rounded-full transition-all ${
                    i === current ? 'w-5 bg-violet-400' : 'w-2 bg-white/20 hover:bg-white/40'
                  }`}
                />
              ))}
            </div>

            <Button
              onClick={isLast ? () => window.close() : next}
              className="gap-1 bg-violet-600 hover:bg-violet-700 text-white"
            >
              {isLast ? (
                <Link href={`/claims/${claimId}`} className="flex items-center gap-1">
                  Done ✓
                </Link>
              ) : (
                <>Next <ChevronRight className="h-4 w-4" /></>
              )}
            </Button>
          </div>

          <p className="mt-3 text-center text-xs text-gray-600">
            Use ← → arrow keys to navigate
          </p>
        </div>
      </div>
    </div>
  )
}
