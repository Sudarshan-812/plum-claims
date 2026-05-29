export type ClaimType =
  | 'CONSULTATION'
  | 'DIAGNOSTIC'
  | 'PHARMACY'
  | 'DENTAL'
  | 'VISION'
  | 'ALTERNATIVE_MEDICINE'

export type ClaimStatus =
  | 'PENDING'
  | 'PROCESSING'
  | 'APPROVED'
  | 'PARTIAL'
  | 'REJECTED'
  | 'MANUAL_REVIEW'
  | 'ERROR'

export type ClaimDecision = 'APPROVED' | 'PARTIAL' | 'REJECTED' | 'MANUAL_REVIEW'

export interface ClaimRecord {
  claim_id: string
  member_id: string
  claim_type: ClaimType
  claimed_amount: number
  treatment_date: string
  status: ClaimStatus
  created_at: string
  updated_at: string
  decision?: ClaimDecision
  approved_amount?: number
  decision_reason?: string
  confidence_score?: number
  trace_id?: string
}

export interface AgentStep {
  agent_name: string
  started_at: string
  completed_at: string
  duration_ms: number
  status: 'SUCCESS' | 'FAILED' | 'SKIPPED'
  input_summary: string
  output_summary: string
  full_input: Record<string, unknown>
  full_output: Record<string, unknown>
  error_message?: string
}

export interface ClaimTrace {
  trace_id: string
  claim_id: string
  started_at: string
  completed_at?: string
  steps: AgentStep[]
  final_decision?: string
  final_confidence?: number
}

export interface ReplayStep {
  step_number: number
  agent_name: string
  title: string
  description: string
  input_summary: string
  output_summary: string
  status: string
  duration_ms: number
  full_data: Record<string, unknown>
}

export const MEMBERS = [
  { id: 'EMP001', name: 'Rajesh Kumar' },
  { id: 'EMP002', name: 'Priya Singh' },
  { id: 'EMP003', name: 'Amit Verma' },
  { id: 'EMP004', name: 'Sneha Reddy' },
  { id: 'EMP005', name: 'Vikram Joshi' },
  { id: 'EMP006', name: 'Kavita Nair' },
  { id: 'EMP007', name: 'Suresh Patil' },
  { id: 'EMP008', name: 'Ravi Menon' },
  { id: 'EMP009', name: 'Anita Desai' },
  { id: 'EMP010', name: 'Deepak Shah' },
]

export const CLAIM_TYPE_LABELS: Record<ClaimType, string> = {
  CONSULTATION: 'Consultation',
  DIAGNOSTIC: 'Diagnostic',
  PHARMACY: 'Pharmacy',
  DENTAL: 'Dental',
  VISION: 'Vision',
  ALTERNATIVE_MEDICINE: 'Alt. Medicine',
}

export const REQUIRED_DOCS: Record<ClaimType, string[]> = {
  CONSULTATION: ['Prescription', 'Hospital Bill'],
  DIAGNOSTIC: ['Prescription', 'Lab Report', 'Hospital Bill'],
  PHARMACY: ['Prescription', 'Pharmacy Bill'],
  DENTAL: ['Hospital Bill'],
  VISION: ['Prescription', 'Hospital Bill'],
  ALTERNATIVE_MEDICINE: ['Prescription', 'Hospital Bill'],
}
