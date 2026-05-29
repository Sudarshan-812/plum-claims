'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { AgentStep as AgentStepType } from '@/lib/types'

interface Props {
  step: AgentStepType
  index: number
}

const agentDescriptions: Record<string, string> = {
  DocumentVerificationAgent: 'Checked that required document types were uploaded',
  DocumentParsingAgent:      'Extracted structured data from your documents using AI',
  FraudDetectionAgent:       'Scanned for unusual claim patterns',
  PolicyEvaluationAgent:     'Applied policy rules: waiting periods, exclusions, limits',
  DecisionAgent:             'Synthesised all checks into a final coverage decision',
  AuditAgent:                'Recorded the complete audit trail',
}

export function AgentStep({ step, index }: Props) {
  const [expanded, setExpanded] = useState(false)

  const isSuccess = step.status === 'SUCCESS'
  const isFailed  = step.status === 'FAILED'

  const statusIcon = isSuccess ? '✓' : isFailed ? '✗' : '○'
  const dotColor   = isSuccess
    ? 'bg-green-500 border-green-500'
    : isFailed
    ? 'bg-red-500 border-red-500'
    : 'bg-gray-300 border-gray-300'

  const lineColor = isSuccess ? 'bg-green-200' : isFailed ? 'bg-red-200' : 'bg-gray-200'

  return (
    <div className="relative flex gap-4">
      {/* Vertical line */}
      <div className="flex flex-col items-center">
        <div
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 text-xs font-bold ${dotColor} ${
            isSuccess ? 'text-white' : isFailed ? 'text-white' : 'text-gray-400'
          }`}
        >
          {statusIcon}
        </div>
        <div className={`mt-1 w-0.5 flex-1 ${lineColor}`} />
      </div>

      {/* Content */}
      <div className="mb-6 flex-1">
        {/* Header row */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-start justify-between rounded-lg border border-gray-200 bg-white px-4 py-3 text-left shadow-sm transition hover:bg-gray-50"
        >
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-gray-900">
                {step.agent_name.replace('Agent', '').replace(/([A-Z])/g, ' $1').trim()}
              </span>
              <span
                className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                  isSuccess
                    ? 'bg-green-100 text-green-700'
                    : isFailed
                    ? 'bg-red-100 text-red-700'
                    : 'bg-gray-100 text-gray-500'
                }`}
              >
                {step.duration_ms}ms
              </span>
              {step.error_message && (
                <span className="rounded bg-red-50 px-1.5 py-0.5 text-xs text-red-600">
                  Failed
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-gray-500">
              {agentDescriptions[step.agent_name] ?? step.agent_name}
            </p>
          </div>
          {expanded ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-gray-400" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-gray-400" />
          )}
        </button>

        {/* Expanded detail */}
        {expanded && (
          <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 p-4 text-xs">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="mb-1 font-semibold uppercase tracking-wide text-gray-400">
                  Input
                </p>
                <pre className="overflow-auto rounded bg-white p-2 text-gray-700 border border-gray-200 max-h-48">
                  {JSON.stringify(step.full_input, null, 2)}
                </pre>
              </div>
              <div>
                <p className="mb-1 font-semibold uppercase tracking-wide text-gray-400">
                  Output
                </p>
                <pre className="overflow-auto rounded bg-white p-2 text-gray-700 border border-gray-200 max-h-48">
                  {JSON.stringify(step.full_output, null, 2)}
                </pre>
              </div>
            </div>
            {step.error_message && (
              <div className="mt-3 rounded bg-red-50 p-2 text-red-700">
                <span className="font-medium">Error: </span>{step.error_message}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
