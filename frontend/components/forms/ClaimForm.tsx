'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { DocumentUpload } from './DocumentUpload'
import { api, formatCurrency } from '@/lib/api'
import { MEMBERS, CLAIM_TYPE_LABELS, type ClaimType } from '@/lib/types'

const CLAIM_TYPES: ClaimType[] = [
  'CONSULTATION', 'DIAGNOSTIC', 'PHARMACY', 'DENTAL', 'VISION', 'ALTERNATIVE_MEDICINE',
]

type Step = 1 | 2 | 3

interface FormData {
  member_id: string
  claim_type: ClaimType
  treatment_date: string
  claimed_amount: string
  notes: string
}

const initialForm: FormData = {
  member_id:      'EMP001',
  claim_type:     'CONSULTATION',
  treatment_date: '',
  claimed_amount: '',
  notes:          '',
}

export function ClaimForm() {
  const router = useRouter()
  const [step, setStep]       = useState<Step>(1)
  const [form, setForm]       = useState<FormData>(initialForm)
  const [files, setFiles]     = useState<File[]>([])
  const [errors, setErrors]   = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted]   = useState<{ claim_id: string; message: string } | null>(null)
  const [submitError, setSubmitError] = useState('')

  const today = new Date().toISOString().split('T')[0]

  function field(name: keyof FormData, value: string) {
    setForm(prev => ({ ...prev, [name]: value }))
    setErrors(prev => { const next = { ...prev }; delete next[name]; return next })
  }

  function validateStep1(): boolean {
    const e: Record<string, string> = {}
    if (!form.member_id)      e.member_id      = 'Required'
    if (!form.claim_type)     e.claim_type     = 'Required'
    if (!form.treatment_date) e.treatment_date = 'Required'
    else if (form.treatment_date > today) e.treatment_date = 'Cannot be in the future'
    if (!form.claimed_amount || parseFloat(form.claimed_amount) <= 0)
      e.claimed_amount = 'Must be > 0'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  function validateStep2(): boolean {
    if (files.length === 0) {
      setErrors({ files: 'Please upload at least one document' })
      return false
    }
    return true
  }

  function nextStep() {
    if (step === 1 && !validateStep1()) return
    if (step === 2 && !validateStep2()) return
    setStep(s => (s < 3 ? ((s + 1) as Step) : s))
  }

  async function handleSubmit() {
    setSubmitting(true)
    setSubmitError('')
    try {
      const claimData = {
        member_id:      form.member_id,
        claim_type:     form.claim_type,
        treatment_date: form.treatment_date,
        claimed_amount: parseFloat(form.claimed_amount),
        notes:          form.notes || undefined,
        documents:      [],
      }
      const result = await api.submitClaim(claimData, files)
      setSubmitted(result)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <Card className="border border-green-200 bg-green-50">
        <CardContent className="p-8 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100 text-3xl">
            ✓
          </div>
          <h2 className="text-xl font-bold text-green-900">Claim Submitted!</h2>
          <p className="mt-1 text-green-700">{submitted.message}</p>
          <p className="mt-2 font-mono text-sm text-green-600">
            Claim ID: {submitted.claim_id.slice(0, 8).toUpperCase()}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link href={`/claims/${submitted.claim_id}`}>
              <Button className="bg-violet-600 hover:bg-violet-700 text-white">
                View Claim
              </Button>
            </Link>
            <Button
              variant="outline"
              onClick={() => {
                setSubmitted(null)
                setForm(initialForm)
                setFiles([])
                setStep(1)
              }}
            >
              Submit Another
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {/* Step progress */}
      <div className="flex items-center gap-2">
        {([1, 2, 3] as Step[]).map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-full text-sm font-medium transition ${
                s < step
                  ? 'bg-violet-600 text-white'
                  : s === step
                  ? 'bg-violet-100 text-violet-700 ring-2 ring-violet-300'
                  : 'bg-gray-100 text-gray-400'
              }`}
            >
              {s < step ? '✓' : s}
            </div>
            <span className={`text-sm ${s === step ? 'font-medium text-gray-900' : 'text-gray-400'}`}>
              {s === 1 ? 'Details' : s === 2 ? 'Documents' : 'Review'}
            </span>
            {i < 2 && <div className="h-px w-8 bg-gray-200" />}
          </div>
        ))}
      </div>

      <Card className="border border-gray-200 bg-white">
        <CardContent className="p-6">
          {/* ── Step 1 ── */}
          {step === 1 && (
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-gray-700">Member ID *</label>
                <select
                  value={form.member_id}
                  onChange={e => field('member_id', e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-200"
                >
                  {MEMBERS.map(m => (
                    <option key={m.id} value={m.id}>{m.id} — {m.name}</option>
                  ))}
                </select>
                {errors.member_id && <p className="mt-1 text-xs text-red-600">{errors.member_id}</p>}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Claim Type *</label>
                <select
                  value={form.claim_type}
                  onChange={e => field('claim_type', e.target.value as ClaimType)}
                  className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-200"
                >
                  {CLAIM_TYPES.map(ct => (
                    <option key={ct} value={ct}>{CLAIM_TYPE_LABELS[ct]}</option>
                  ))}
                </select>
              </div>

              <div className="grid gap-5 sm:grid-cols-2">
                <div>
                  <label className="block text-sm font-medium text-gray-700">Treatment Date *</label>
                  <input
                    type="date"
                    max={today}
                    value={form.treatment_date}
                    onChange={e => field('treatment_date', e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-200"
                  />
                  {errors.treatment_date && <p className="mt-1 text-xs text-red-600">{errors.treatment_date}</p>}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700">Claimed Amount (₹) *</label>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    placeholder="0"
                    value={form.claimed_amount}
                    onChange={e => field('claimed_amount', e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-200"
                  />
                  {errors.claimed_amount && <p className="mt-1 text-xs text-red-600">{errors.claimed_amount}</p>}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Notes (optional)</label>
                <textarea
                  rows={2}
                  placeholder="Any additional context..."
                  value={form.notes}
                  onChange={e => field('notes', e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-200"
                />
              </div>
            </div>
          )}

          {/* ── Step 2 ── */}
          {step === 2 && (
            <div>
              <DocumentUpload
                claimType={form.claim_type}
                files={files}
                onChange={setFiles}
              />
              {errors.files && <p className="mt-2 text-xs text-red-600">{errors.files}</p>}
            </div>
          )}

          {/* ── Step 3 ── */}
          {step === 3 && (
            <div className="space-y-4">
              <h3 className="font-medium text-gray-900">Review Your Submission</h3>
              <div className="rounded-lg border border-gray-200 divide-y divide-gray-100">
                {[
                  ['Member', `${form.member_id} — ${MEMBERS.find(m => m.id === form.member_id)?.name}`],
                  ['Claim Type', CLAIM_TYPE_LABELS[form.claim_type]],
                  ['Treatment Date', form.treatment_date],
                  ['Claimed Amount', formatCurrency(parseFloat(form.claimed_amount) || 0)],
                  ['Documents', `${files.length} file(s): ${files.map(f => f.name).join(', ')}`],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-start gap-4 px-4 py-3">
                    <span className="w-36 shrink-0 text-sm text-gray-500">{label}</span>
                    <span className="text-sm font-medium text-gray-900">{value}</span>
                  </div>
                ))}
                {form.notes && (
                  <div className="flex items-start gap-4 px-4 py-3">
                    <span className="w-36 shrink-0 text-sm text-gray-500">Notes</span>
                    <span className="text-sm text-gray-700">{form.notes}</span>
                  </div>
                )}
              </div>
              {submitError && (
                <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                  {submitError}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Navigation */}
      <div className="flex justify-between">
        {step > 1 ? (
          <Button variant="outline" onClick={() => setStep(s => (s - 1) as Step)}>
            ← Back
          </Button>
        ) : (
          <Link href="/">
            <Button variant="outline">Cancel</Button>
          </Link>
        )}

        {step < 3 ? (
          <Button onClick={nextStep} className="bg-violet-600 hover:bg-violet-700 text-white">
            Continue →
          </Button>
        ) : (
          <Button
            onClick={handleSubmit}
            disabled={submitting}
            className="bg-violet-600 hover:bg-violet-700 text-white"
          >
            {submitting ? 'Submitting…' : 'Submit Claim'}
          </Button>
        )}
      </div>
    </div>
  )
}
