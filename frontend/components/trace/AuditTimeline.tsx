'use client'

import type { ClaimTrace } from '@/lib/types'
import { AgentStep } from './AgentStep'

interface Props {
  trace: ClaimTrace
}

export function AuditTimeline({ trace }: Props) {
  if (!trace.steps.length) {
    return (
      <div className="py-8 text-center text-sm text-gray-500">
        No trace steps available yet.
      </div>
    )
  }

  const totalMs = trace.steps.reduce((sum, s) => sum + s.duration_ms, 0)

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm font-medium uppercase tracking-wide text-gray-400">
          Processing Timeline
        </p>
        <span className="text-xs text-gray-500">
          {trace.steps.length} steps · {totalMs}ms total
        </span>
      </div>

      <div className="space-y-0">
        {trace.steps.map((step, i) => (
          <AgentStep key={`${step.agent_name}-${i}`} step={step} index={i} />
        ))}
      </div>

      {trace.final_decision && (
        <div className="mt-2 rounded-lg border border-violet-200 bg-violet-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-500">
            Final Decision
          </p>
          <p className="mt-0.5 text-sm font-bold text-violet-900">
            {trace.final_decision}
            {trace.final_confidence != null && (
              <span className="ml-2 font-normal text-violet-600">
                · {Math.round(trace.final_confidence * 100)}% confidence
              </span>
            )}
          </p>
        </div>
      )}
    </div>
  )
}
