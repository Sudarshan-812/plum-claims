'use client'

import { useEffect, useCallback } from 'react'
import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import type { ReplayStep } from '@/lib/types'

interface Props {
  steps: ReplayStep[]
  currentIndex: number
  onClose: () => void
  onPrev: () => void
  onNext: () => void
}

const stepIcons: Record<string, string> = {
  DocumentVerificationAgent: '🔍',
  DocumentParsingAgent:      '📄',
  FraudDetectionAgent:       '🛡️',
  PolicyEvaluationAgent:     '📋',
  DecisionAgent:             '⚖️',
  AuditAgent:                '💾',
}

function renderStepContent(step: ReplayStep) {
  const output = step.full_data?.output as Record<string, unknown> | undefined

  if (step.agent_name === 'DocumentVerificationAgent') {
    const status = (output?.status as string) ?? 'UNKNOWN'
    const missing = (output?.missing_required as string[]) ?? []
    return (
      <div className="space-y-2 text-sm">
        <div className={`rounded-lg p-3 ${status === 'PASS' ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
          <p className={`font-medium ${status === 'PASS' ? 'text-green-800' : 'text-red-800'}`}>
            {status === 'PASS' ? '✓ All required documents present' : '✗ Document verification failed'}
          </p>
          {missing.length > 0 && (
            <p className="mt-1 text-red-600">Missing: {missing.join(', ')}</p>
          )}
        </div>
      </div>
    )
  }

  if (step.agent_name === 'FraudDetectionAgent') {
    const flags = (output?.fraud_flags as string[]) ?? []
    const score = (output?.fraud_score as number) ?? 0
    const autoReview = (output?.auto_manual_review as boolean) ?? false
    return (
      <div className="space-y-3 text-sm">
        <div className="flex items-center gap-3">
          <span className="font-medium text-gray-700">Fraud Score:</span>
          <Progress value={score * 100} className="h-2 flex-1" />
          <span className={`font-mono font-bold ${score < 0.3 ? 'text-green-600' : score < 0.7 ? 'text-amber-600' : 'text-red-600'}`}>
            {(score * 100).toFixed(0)}%
          </span>
        </div>
        {flags.length === 0 ? (
          <p className="text-green-700">✓ No fraud signals detected</p>
        ) : (
          <ul className="space-y-1">
            {flags.map((f, i) => (
              <li key={i} className="text-amber-700">⚠ {f}</li>
            ))}
          </ul>
        )}
        {autoReview && (
          <p className="rounded bg-blue-50 p-2 text-blue-700">
            → Routed to manual review
          </p>
        )}
      </div>
    )
  }

  if (step.agent_name === 'PolicyEvaluationAgent') {
    const eligible = output?.eligible_amount as Record<string, unknown> | undefined
    const waiting  = output?.waiting_period as Record<string, unknown> | undefined
    const preAuth  = output?.pre_auth as Record<string, unknown> | undefined
    return (
      <div className="space-y-2 text-sm">
        {waiting && (
          <div className={`rounded-lg p-2 ${waiting.passed ? 'bg-green-50 border border-green-100' : 'bg-red-50 border border-red-100'}`}>
            <span className={waiting.passed ? 'text-green-700' : 'text-red-700'}>
              {waiting.passed ? '✓' : '✗'} Waiting Period: {String(waiting.reason ?? '')}
            </span>
          </div>
        )}
        {preAuth && (preAuth.required as boolean) && (
          <div className="rounded-lg bg-red-50 border border-red-100 p-2 text-red-700">
            ✗ Pre-authorisation required
          </div>
        )}
        {eligible && (
          <div className="rounded-lg bg-gray-50 border border-gray-200 p-2">
            <p className="font-medium text-gray-700">
              Eligible Amount: <span className="text-violet-700">{String(eligible.eligible_amount ?? '—')}</span>
            </p>
            {(eligible.calculation_breakdown as string[] | undefined)?.slice(-2).map((b, i) => (
              <p key={i} className="text-xs text-gray-500 mt-0.5">{b}</p>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (step.agent_name === 'DecisionAgent') {
    const decision  = output?.decision as string | undefined
    const amount    = output?.approved_amount as number | undefined
    const confidence = output?.confidence_score as number | undefined
    return (
      <div className="text-sm">
        <div className={`rounded-xl p-4 text-center ${
          decision === 'APPROVED' ? 'bg-green-50 border border-green-200' :
          decision === 'PARTIAL'  ? 'bg-amber-50 border border-amber-200' :
          decision === 'REJECTED' ? 'bg-red-50 border border-red-200' :
                                    'bg-blue-50 border border-blue-200'
        }`}>
          <p className="text-2xl font-bold">{decision}</p>
          {amount != null && amount > 0 && (
            <p className="mt-1 text-lg font-semibold text-gray-700">
              ₹{amount.toLocaleString('en-IN')}
            </p>
          )}
          {confidence != null && (
            <div className="mt-2 flex items-center justify-center gap-2">
              <Progress value={confidence * 100} className="h-2 w-24" />
              <span className="text-xs text-gray-500">{Math.round(confidence * 100)}% confident</span>
            </div>
          )}
        </div>
      </div>
    )
  }

  // Generic: show output summary
  return (
    <div className="rounded-lg bg-gray-50 p-3 text-sm text-gray-700">
      <p>{step.output_summary}</p>
    </div>
  )
}

export function ReplayModal({ steps, currentIndex, onClose, onPrev, onNext }: Props) {
  const step = steps[currentIndex]

  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') onNext()
      if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   onPrev()
      if (e.key === 'Escape') onClose()
    },
    [onNext, onPrev, onClose]
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [handleKey])

  if (!step) return null

  const icon = stepIcons[step.agent_name] ?? '📌'
  const isLast = currentIndex === steps.length - 1

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="relative flex max-h-[90vh] w-full max-w-lg flex-col rounded-2xl bg-white shadow-2xl">
        {/* Close */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Step indicator */}
        <div className="px-6 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-500">
            Step {currentIndex + 1} of {steps.length}
          </p>
          <h2 className="mt-1 text-xl font-bold text-gray-900">
            {icon} {step.title}
          </h2>
          <p className="mt-1 text-sm text-gray-500">{step.description}</p>
        </div>

        {/* Content */}
        <div className="mt-4 flex-1 overflow-y-auto px-6 pb-2">
          {renderStepContent(step)}

          {/* Timing */}
          <div className="mt-4 flex items-center justify-between text-xs text-gray-400">
            <span>Duration: {step.duration_ms}ms</span>
            <span className={`rounded px-1.5 py-0.5 ${step.status === 'SUCCESS' ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}`}>
              {step.status}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <div className="border-t border-gray-100 px-6 py-4">
          <div className="flex items-center justify-between">
            <Button
              variant="outline"
              size="sm"
              onClick={onPrev}
              disabled={currentIndex === 0}
              className="gap-1"
            >
              <ChevronLeft className="h-4 w-4" /> Previous
            </Button>

            {/* Dots */}
            <div className="flex gap-1.5">
              {steps.map((_, i) => (
                <span
                  key={i}
                  className={`h-2 w-2 rounded-full transition ${
                    i === currentIndex ? 'bg-violet-600 w-4' : 'bg-gray-300'
                  }`}
                />
              ))}
            </div>

            <Button
              size="sm"
              onClick={isLast ? onClose : onNext}
              className="gap-1 bg-violet-600 hover:bg-violet-700 text-white"
            >
              {isLast ? 'Finish' : <>Next <ChevronRight className="h-4 w-4" /></>}
            </Button>
          </div>
          <p className="mt-2 text-center text-xs text-gray-400">
            Use ← → arrow keys to navigate
          </p>
        </div>
      </div>
    </div>
  )
}
