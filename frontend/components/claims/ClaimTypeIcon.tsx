'use client'

import type { ClaimType } from '@/lib/types'

const icons: Record<ClaimType, string> = {
  CONSULTATION:        '🩺',
  DIAGNOSTIC:          '🔬',
  PHARMACY:            '💊',
  DENTAL:              '🦷',
  VISION:              '👁️',
  ALTERNATIVE_MEDICINE:'🌿',
}

export function ClaimTypeIcon({ type }: { type: ClaimType }) {
  return <span title={type}>{icons[type] ?? '📋'}</span>
}
