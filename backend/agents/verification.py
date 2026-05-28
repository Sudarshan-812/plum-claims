"""Document verification agent — checks that the right docs are present."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from models.claim import DocumentType, UploadedDocument
from services.policy_engine import PolicyEngine

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result returned by DocumentVerificationAgent.verify()."""

    status: Literal["PASS", "FAIL"]
    missing_required: list[str] = field(default_factory=list)
    unexpected_documents: list[str] = field(default_factory=list)
    error_message: str | None = None
    checked_at: datetime = field(default_factory=datetime.utcnow)


# Maps keywords found in filenames to DocumentType values.
_FILENAME_KEYWORD_MAP: list[tuple[list[str], DocumentType]] = [
    (["prescription", "rx", "doctor", "consult"], DocumentType.PRESCRIPTION),
    (["discharge", "summary", "discharge_summary"], DocumentType.DISCHARGE_SUMMARY),
    (["dental", "tooth", "teeth", "orthodon"], DocumentType.DENTAL_REPORT),
    (["pharmacy", "medicine", "drug", "chemist"], DocumentType.PHARMACY_BILL),
    (["lab", "report", "test", "result", "pathology", "blood"], DocumentType.LAB_REPORT),
    (["diagnostic", "xray", "x-ray", "scan", "mri", "ct", "ultrasound"], DocumentType.DIAGNOSTIC_REPORT),
    (["bill", "invoice", "receipt", "hospital"], DocumentType.HOSPITAL_BILL),
]

# Human-readable names for document types used in error messages.
_DOC_TYPE_LABELS: dict[str, str] = {
    "PRESCRIPTION": "Doctor's Prescription",
    "HOSPITAL_BILL": "Hospital Bill / Invoice",
    "LAB_REPORT": "Lab Report",
    "PHARMACY_BILL": "Pharmacy Bill",
    "DENTAL_REPORT": "Dental Report",
    "DISCHARGE_SUMMARY": "Discharge Summary",
    "DIAGNOSTIC_REPORT": "Diagnostic Report",
    "UNKNOWN": "Unknown Document",
}


def _label(doc_type: str) -> str:
    """Return a human-readable label for a document type string."""
    return _DOC_TYPE_LABELS.get(doc_type.upper(), doc_type)


class DocumentVerificationAgent:
    """
    Verifies that the documents uploaded with a claim match the requirements
    defined in the policy for that claim type.
    """

    def __init__(self, policy_engine: PolicyEngine) -> None:
        """Initialise with a loaded PolicyEngine instance."""
        self.policy_engine = policy_engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(
        self,
        claim_type: str,
        uploaded_documents: list[UploadedDocument],
    ) -> VerificationResult:
        """
        Check whether the uploaded documents satisfy the policy requirements.

        Returns a VerificationResult with status PASS or FAIL.  On failure
        the error_message is specific and actionable — it names exactly
        which documents are missing and what they must contain.
        """
        logger.info(
            "DocumentVerificationAgent.verify started: claim_type=%s, doc_count=%d",
            claim_type,
            len(uploaded_documents),
        )

        # Empty submission is always a failure
        if not uploaded_documents:
            result = VerificationResult(
                status="FAIL",
                missing_required=[],
                unexpected_documents=[],
                error_message=(
                    "No documents were uploaded. Please attach the required documents "
                    "for your claim before submitting."
                ),
            )
            logger.info("DocumentVerificationAgent.verify completed: status=FAIL (no documents)")
            return result

        requirements = self.policy_engine.get_required_documents(claim_type)
        required: list[str] = requirements["required"]

        # Collect the document types that were actually submitted
        submitted_types = {doc.document_type.value for doc in uploaded_documents}

        # Find which required types are missing
        missing_required = [r for r in required if r not in submitted_types]

        # Determine unexpected docs: types that are neither required nor optional
        optional_types = set(requirements.get("optional", []))
        known_types = set(required) | optional_types
        unexpected_docs = [
            doc.filename
            for doc in uploaded_documents
            if doc.document_type.value not in known_types
            and doc.document_type != DocumentType.UNKNOWN
        ]

        if missing_required:
            error_message = self._build_error_message(
                claim_type=claim_type,
                required=required,
                missing=missing_required,
                submitted=list(submitted_types),
            )
            result = VerificationResult(
                status="FAIL",
                missing_required=missing_required,
                unexpected_documents=unexpected_docs,
                error_message=error_message,
            )
            logger.info(
                "DocumentVerificationAgent.verify completed: status=FAIL, missing=%s",
                missing_required,
            )
            return result

        result = VerificationResult(
            status="PASS",
            missing_required=[],
            unexpected_documents=unexpected_docs,
        )
        logger.info("DocumentVerificationAgent.verify completed: status=PASS")
        return result

    def detect_document_type(self, filename: str) -> DocumentType:
        """
        Infer DocumentType from keywords in the filename.

        Checks are ordered from most specific to least specific.
        Returns UNKNOWN when no keyword matches.
        """
        name_lower = filename.lower().replace("-", "_").replace(" ", "_")
        for keywords, doc_type in _FILENAME_KEYWORD_MAP:
            if any(kw in name_lower for kw in keywords):
                return doc_type
        return DocumentType.UNKNOWN

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_error_message(
        self,
        claim_type: str,
        required: list[str],
        missing: list[str],
        submitted: list[str],
    ) -> str:
        """
        Build a specific, actionable error message for a document failure.

        Example output::

            Your PHARMACY claim requires a Doctor's Prescription and a
            Pharmacy Bill. We received: Lab Report.
            Please upload:
              (1) Doctor's Prescription — showing medicines prescribed,
                  doctor's name, date and signature.
              (2) Pharmacy Bill — with drug license number and itemised
                  medicines.
        """
        required_labels = " and ".join(_label(r) for r in required)
        submitted_labels = (
            ", ".join(_label(s) for s in submitted) if submitted else "nothing"
        )

        lines = [
            f"Your {claim_type.upper()} claim requires {required_labels}.",
            f"We received: {submitted_labels}.",
            "Please upload:",
        ]

        guidance = _DOC_UPLOAD_GUIDANCE
        for idx, doc_type in enumerate(missing, start=1):
            hint = guidance.get(doc_type, f"A valid {_label(doc_type)}.")
            lines.append(f"  ({idx}) {_label(doc_type)} — {hint}")

        return "\n".join(lines)


# Actionable upload guidance per document type.
_DOC_UPLOAD_GUIDANCE: dict[str, str] = {
    "PRESCRIPTION": (
        "showing medicines prescribed, doctor's name, registration number, date and signature."
    ),
    "HOSPITAL_BILL": (
        "itemised bill on hospital letterhead showing patient name, diagnosis, "
        "date of service and hospital stamp."
    ),
    "LAB_REPORT": (
        "showing patient name, test name(s), values, reference ranges and lab stamp."
    ),
    "PHARMACY_BILL": (
        "with drug license number, pharmacy name, itemised medicines with batch numbers and amounts."
    ),
    "DENTAL_REPORT": (
        "from a registered dentist showing procedure(s) performed, tooth number(s) and date."
    ),
    "DISCHARGE_SUMMARY": (
        "from the hospital showing admission date, discharge date, diagnosis and treatment summary."
    ),
    "DIAGNOSTIC_REPORT": (
        "showing patient name, test type, findings, date and radiologist/pathologist signature."
    ),
}
