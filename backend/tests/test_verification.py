"""Tests for DocumentVerificationAgent."""

from __future__ import annotations

from datetime import datetime

import pytest

from models.claim import DocumentType, UploadedDocument


def _doc(filename: str, doc_type: DocumentType, size: int = 1024) -> UploadedDocument:
    """Helper to build an UploadedDocument quickly."""
    return UploadedDocument(
        filename=filename,
        document_type=doc_type,
        file_size_bytes=size,
        upload_timestamp=datetime.utcnow(),
    )


@pytest.fixture
def agent(engine):
    from agents.verification import DocumentVerificationAgent
    return DocumentVerificationAgent(engine)


# ------------------------------------------------------------------
# PASS cases
# ------------------------------------------------------------------

class TestVerificationPass:
    def test_pharmacy_claim_correct_docs(self, agent):
        docs = [
            _doc("prescription.pdf", DocumentType.PRESCRIPTION),
            _doc("pharmacy_bill.pdf", DocumentType.PHARMACY_BILL),
        ]
        result = agent.verify("PHARMACY", docs)
        assert result.status == "PASS"
        assert result.missing_required == []
        assert result.error_message is None

    def test_consultation_claim_all_optional_docs(self, agent):
        """Consultation only requires HOSPITAL_BILL; optionals should not cause failure."""
        docs = [
            _doc("hospital_bill.pdf", DocumentType.HOSPITAL_BILL),
            _doc("prescription.pdf", DocumentType.PRESCRIPTION),
            _doc("lab_report.pdf", DocumentType.LAB_REPORT),
        ]
        result = agent.verify("CONSULTATION", docs)
        assert result.status == "PASS"

    def test_diagnostic_claim_with_required_doc(self, agent):
        docs = [_doc("diagnostic_report.pdf", DocumentType.DIAGNOSTIC_REPORT)]
        result = agent.verify("DIAGNOSTIC", docs)
        assert result.status == "PASS"

    def test_dental_claim_with_both_required(self, agent):
        docs = [
            _doc("dental_report.pdf", DocumentType.DENTAL_REPORT),
            _doc("hospital_invoice.pdf", DocumentType.HOSPITAL_BILL),
        ]
        result = agent.verify("DENTAL", docs)
        assert result.status == "PASS"


# ------------------------------------------------------------------
# FAIL cases
# ------------------------------------------------------------------

class TestVerificationFail:
    def test_pharmacy_missing_prescription(self, agent):
        docs = [_doc("pharmacy_bill.pdf", DocumentType.PHARMACY_BILL)]
        result = agent.verify("PHARMACY", docs)
        assert result.status == "FAIL"
        assert "PRESCRIPTION" in result.missing_required
        # Error message must name the claim type and what is missing
        assert "PHARMACY" in result.error_message
        assert "Prescription" in result.error_message

    def test_pharmacy_missing_pharmacy_bill(self, agent):
        docs = [_doc("prescription.pdf", DocumentType.PRESCRIPTION)]
        result = agent.verify("PHARMACY", docs)
        assert result.status == "FAIL"
        assert "PHARMACY_BILL" in result.missing_required

    def test_diagnostic_wrong_docs_uploaded(self, agent):
        docs = [_doc("pharmacy_bill.pdf", DocumentType.PHARMACY_BILL)]
        result = agent.verify("DIAGNOSTIC", docs)
        assert result.status == "FAIL"
        assert "DIAGNOSTIC_REPORT" in result.missing_required

    def test_empty_documents_list_fails(self, agent):
        result = agent.verify("PHARMACY", [])
        assert result.status == "FAIL"
        assert "No documents" in result.error_message

    def test_unknown_document_types_fails_pharmacy(self, agent):
        docs = [_doc("random_file.pdf", DocumentType.UNKNOWN)]
        result = agent.verify("PHARMACY", docs)
        assert result.status == "FAIL"

    def test_error_message_is_specific_not_generic(self, agent):
        """Error message must be actionable — not just 'Wrong documents'."""
        docs = [_doc("lab_report.pdf", DocumentType.LAB_REPORT)]
        result = agent.verify("PHARMACY", docs)
        assert result.status == "FAIL"
        # Should name the claim type
        assert "PHARMACY" in result.error_message
        # Should tell the user what to upload
        assert "upload" in result.error_message.lower() or "require" in result.error_message.lower()
        # Should NOT be a vague one-liner
        assert len(result.error_message) > 80


# ------------------------------------------------------------------
# detect_document_type
# ------------------------------------------------------------------

class TestDetectDocumentType:
    def test_prescription_detection(self, agent):
        assert agent.detect_document_type("doctor_prescription.pdf") == DocumentType.PRESCRIPTION

    def test_rx_detected_as_prescription(self, agent):
        assert agent.detect_document_type("rx_2024.jpg") == DocumentType.PRESCRIPTION

    def test_pharmacy_bill_detection(self, agent):
        assert agent.detect_document_type("pharmacy_receipt.pdf") == DocumentType.PHARMACY_BILL

    def test_lab_report_detection(self, agent):
        assert agent.detect_document_type("blood_test_result.pdf") == DocumentType.LAB_REPORT

    def test_hospital_bill_detection(self, agent):
        assert agent.detect_document_type("hospital_invoice_2024.pdf") == DocumentType.HOSPITAL_BILL

    def test_dental_report_detection(self, agent):
        assert agent.detect_document_type("dental_checkup.pdf") == DocumentType.DENTAL_REPORT

    def test_discharge_summary_detection(self, agent):
        assert agent.detect_document_type("discharge_summary.pdf") == DocumentType.DISCHARGE_SUMMARY

    def test_unknown_filename_returns_unknown(self, agent):
        assert agent.detect_document_type("document_12345.pdf") == DocumentType.UNKNOWN

    def test_diagnostic_xray_detection(self, agent):
        assert agent.detect_document_type("chest_xray.jpg") == DocumentType.DIAGNOSTIC_REPORT
