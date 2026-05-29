import Link from 'next/link'
import { ChevronLeft } from 'lucide-react'
import { ClaimForm } from '@/components/forms/ClaimForm'

export default function NewClaimPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-2xl px-4 py-5 sm:px-6">
          <Link
            href="/"
            className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
          >
            <ChevronLeft className="h-4 w-4" />
            Back to Dashboard
          </Link>
          <h1 className="mt-2 text-2xl font-bold text-gray-900">Submit New Claim</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            Fill in the details below to submit a health insurance claim.
          </p>
        </div>
      </div>

      <div className="mx-auto max-w-2xl px-4 py-8 sm:px-6">
        <ClaimForm />
      </div>
    </div>
  )
}
