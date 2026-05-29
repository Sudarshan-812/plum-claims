'use client'

import Link from 'next/link'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { ClaimStatusBadge } from './ClaimStatusBadge'
import { ClaimTypeIcon } from './ClaimTypeIcon'
import { formatCurrency, formatDate, shortId } from '@/lib/api'
import { CLAIM_TYPE_LABELS } from '@/lib/types'
import type { ClaimRecord } from '@/lib/types'

interface Props {
  claims: ClaimRecord[]
}

export function ClaimTable({ claims }: Props) {
  if (claims.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-white py-16 text-center">
        <p className="text-2xl">📋</p>
        <p className="mt-2 font-medium text-gray-700">No claims yet</p>
        <p className="mt-1 text-sm text-gray-500">
          Submit your first claim to get started.
        </p>
        <Link href="/claims/new">
          <Button className="mt-4 bg-violet-600 hover:bg-violet-700 text-white" size="sm">
            + New Claim
          </Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      <Table>
        <TableHeader>
          <TableRow className="border-gray-200 bg-gray-50">
            <TableHead className="text-xs font-medium text-gray-500">CLAIM ID</TableHead>
            <TableHead className="text-xs font-medium text-gray-500">MEMBER</TableHead>
            <TableHead className="text-xs font-medium text-gray-500">TYPE</TableHead>
            <TableHead className="text-xs font-medium text-gray-500">CLAIMED</TableHead>
            <TableHead className="text-xs font-medium text-gray-500">APPROVED</TableHead>
            <TableHead className="text-xs font-medium text-gray-500">STATUS</TableHead>
            <TableHead className="text-xs font-medium text-gray-500">CONFIDENCE</TableHead>
            <TableHead className="text-xs font-medium text-gray-500">DATE</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {claims.map(claim => (
            <TableRow key={claim.claim_id} className="border-gray-100 hover:bg-gray-50">
              <TableCell className="font-mono text-xs text-gray-600">
                {shortId(claim.claim_id)}
              </TableCell>
              <TableCell className="text-sm text-gray-700">{claim.member_id}</TableCell>
              <TableCell>
                <span className="flex items-center gap-1.5 text-sm text-gray-700">
                  <ClaimTypeIcon type={claim.claim_type} />
                  {CLAIM_TYPE_LABELS[claim.claim_type]}
                </span>
              </TableCell>
              <TableCell className="font-mono text-sm text-gray-900">
                {formatCurrency(claim.claimed_amount)}
              </TableCell>
              <TableCell className="font-mono text-sm text-gray-900">
                {claim.approved_amount != null
                  ? formatCurrency(claim.approved_amount)
                  : <span className="text-gray-400">—</span>}
              </TableCell>
              <TableCell>
                <ClaimStatusBadge status={claim.status} />
              </TableCell>
              <TableCell>
                {claim.confidence_score != null ? (
                  <div className="flex items-center gap-2 min-w-[80px]">
                    <Progress
                      value={claim.confidence_score * 100}
                      className="h-1.5 w-14"
                    />
                    <span className="text-xs text-gray-500">
                      {Math.round(claim.confidence_score * 100)}%
                    </span>
                  </div>
                ) : (
                  <span className="text-gray-400 text-sm">—</span>
                )}
              </TableCell>
              <TableCell className="text-xs text-gray-500">
                {formatDate(claim.created_at)}
              </TableCell>
              <TableCell>
                <Link href={`/claims/${claim.claim_id}`}>
                  <Button variant="ghost" size="sm" className="text-violet-600 hover:text-violet-700 hover:bg-violet-50">
                    View
                  </Button>
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
