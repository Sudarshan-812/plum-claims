import type { ClaimRecord, ClaimTrace, ReplayStep } from './types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { ...options?.headers },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  async submitClaim(
    claimData: object,
    files: File[]
  ): Promise<{ claim_id: string; status: string; message: string }> {
    const form = new FormData()
    form.append('claim_data', JSON.stringify(claimData))
    for (const file of files) {
      form.append('files', file)
    }
    const res = await fetch(`${API_URL}/api/claims`, {
      method: 'POST',
      body: form,
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({ message: 'Submission failed' }))
      throw new Error(data.message || `Error ${res.status}`)
    }
    return res.json()
  },

  getClaims(): Promise<ClaimRecord[]> {
    return request<ClaimRecord[]>('/api/claims')
  },

  getClaim(claimId: string): Promise<{ claim: ClaimRecord; trace: ClaimTrace | null }> {
    return request<{ claim: ClaimRecord; trace: ClaimTrace | null }>(`/api/claims/${claimId}`)
  },

  getTrace(claimId: string): Promise<ClaimTrace> {
    return request<ClaimTrace>(`/api/claims/${claimId}/trace`)
  },

  getReplay(claimId: string): Promise<{ steps: ReplayStep[]; final_decision?: string }> {
    return request<{ steps: ReplayStep[]; final_decision?: string }>(
      `/api/claims/${claimId}/replay`
    )
  },

  async reprocess(claimId: string): Promise<void> {
    await request(`/api/claims/${claimId}/reprocess`, { method: 'POST' })
  },
}

export function formatCurrency(amount: number): string {
  return '₹' + amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function shortId(claimId: string): string {
  return claimId.slice(0, 8).toUpperCase()
}
