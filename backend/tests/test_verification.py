"""Tests for DocumentVerificationAgent — aligned with PLUM_GHI_2024 document requirements."""

from __future__ import annotations

from datetime import datetime

import pytest

from models.claim import DocumentType, UploadedDocument


def _doc(filename: str, doc_type: DocumentType, size: int = 1024) -> UploadedDocument:
    return UploadedDocument(
        filename=filename,
        document_type=doc_type,
        file_size_bytes=size,
        upload_timestamp=datetime.now(),
    )


@pytest.fixture
def agent(engine):
    from agents.verification import DocumentVerificationAgent
    return DocumentVerificationAgent(engine)


# ------------------------------------------------------------------
# PASS cases
# ------------------------------------------------------------------

class TestVerificationPass:
    def test_consultation_with_prescription_and_bill(self, agent):
        # PLUM_GHI_2024: CONSULTATION requires PRESCRIPTION + HOSPITAL_BILL
        docs = [
            _doc("prescription.pdf", DocumentType.PRESCRIPTION),
            _doc("hospital_bill.pdf", DocumentType.HOSPITAL_BILL),
        ]
        result = agent.verify("CONSULTATION", docs)
        assert result.status == "PASS"
        assert result.missing_required == []

    def test_consultation_with_optional_lab_report(self, agent):
        docs = [
            _doc("prescription.pdf", DocumentType.PRESCRIPTION),
            _doc("hospital_bill.pdf", DocumentType.HOSPITAL_BILL),
            _doc("lab_report.pdf", DocumentType.LAB_REPORT),
        ]
        result = agent.verify("CONSULTATION", docs)
        assert result.status == "PASS"

    def test_pharmacy_with_prescription_and_bill(self, agent):
        docs = [
            _doc("prescription.pdf", DocumentType.PRESCRIPTION),
            _doc("pharmacy_bill.pdf", DocumentType.PHARMACY_BILL),
        ]
        result = agent.verify("PHARMACY", docs)
        assert result.status == "PASS"

    def test_dental_with_hospital_bill_only(self, agent):
        # DENTAL requires only HOSPITAL_BILL; prescription is optional
        docs = [_doc("hospital_invoice.pdf", DocumentType.HOSPITAL_BILL)]
        result = agent.verify("DENTAL", docs)
        assert result.status == "PASS"

    def test_diagnostic_with_all_required(self, agent):
        # DIAGNOSTIC requires PRESCRIPTION + LAB_REPORT + HOSPITAL_BILL
        docs = [
            _doc("prescription.pdf", DocumentType.PRESCRIPTION),
            _doc("lab_report.pdf", DocumentType.LAB_REPORT),
            _doc("hospital_bill.pdf", DocumentType.HOSPITAL_BILL),
        ]
        result = agent.verify("DIAGNOSTIC", docs)
        assert result.status == "PASS"


# ------------------------------------------------------------------
# FAIL cases
# ------------------------------------------------------------------

class TestVerificationFail:
    def test_consultation_tc001_two_prescriptions_no_bill(self, agent):
        """TC001: two prescriptions uploaded for consultation — hospital bill missing."""
        docs = [
            _doc("dr_sharma_prescription.jpg", DocumentType.PRESCRIPTION),
            _doc("another_prescription.jpg", DocumentType.PRESCRIPTION),
        ]
        result = agent.verify("CONSULTATION", docs)
        assert result.status == "FAIL"
        assert "HOSPITAL_BILL" in result.missing_required
        # Error must name the required type AND what was received
        assert "CONSULTATION" in result.error_message
        assert "Hospital Bill" in result.error_message or "hospital" in result.error_message.lower()

    def test_pharmacy_missing_prescription(self, agent):
        docs = [_doc("pharmacy_bill.pdf", DocumentType.PHARMACY_BILL)]
        result = agent.verify("PHARMACY", docs)
        assert result.status == "FAIL"
        assert "PRESCRIPTION" in result.missing_required
        assert "PHARMACY" in result.error_message

    def test_pharmacy_missing_pharmacy_bill(self, agent):
        docs = [_doc("prescription.pdf", DocumentType.PRESCRIPTION)]
        result = agent.verify("PHARMACY", docs)
        assert result.status == "FAIL"
        assert "PHARMACY_BILL" in result.missing_required

    def test_diagnostic_missing_lab_report(self, agent):
        docs = [
            _doc("prescription.pdf", DocumentType.PRESCRIPTION),
            _doc("hospital_bill.pdf", DocumentType.HOSPITAL_BILL),
        ]
        result = agent.verify("DIAGNOSTIC", docs)
        assert result.status == "FAIL"
        assert "LAB_REPORT" in result.missing_required

    def test_empty_documents_list_fails(self, agent):
        result = agent.verify("CONSULTATION", [])
        assert result.status == "FAIL"
        assert "No documents" in result.error_message

    def test_error_message_is_specific_not_generic(self, agent):
        """Error message must be actionable, not a one-liner."""
        docs = [_doc("lab_report.pdf", DocumentType.LAB_REPORT)]
        result = agent.verify("PHARMACY", docs)
        assert result.status == "FAIL"
        assert "PHARMACY" in result.error_message
        assert len(result.error_message) > 80
        assert "upload" in result.error_message.lower() or "require" in result.error_message.lower()

    def test_error_message_names_missing_type(self, agent):
        """TC001 spec: message must name what was uploaded AND what is needed."""
        docs = [_doc("prescription.jpg", DocumentType.PRESCRIPTION)]
        result = agent.verify("CONSULTATION", docs)
        assert result.status == "FAIL"
        # Must reference the missing document type
        assert any(
            term in result.error_message
            for term in ["Hospital Bill", "HOSPITAL_BILL", "hospital bill"]
        )


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

    def test_xray_detected_as_diagnostic(self, agent):
        assert agent.detect_document_type("chest_xray.jpg") == DocumentType.DIAGNOSTIC_REPORT
