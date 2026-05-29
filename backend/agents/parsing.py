"""Document parsing agent — uses Claude Vision to extract data from documents."""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime
from typing import Optional

from models.claim import DocumentParsingResult, DocumentType, ExtractedLineItem

logger = logging.getLogger(__name__)

_CRITICAL_FIELDS: dict[str, list[str]] = {
    "PRESCRIPTION":    ["patient_name", "doctor_name", "diagnosis", "treatment_date"],
    "HOSPITAL_BILL":   ["patient_name", "hospital_name", "total_amount", "bill_date"],
    "LAB_REPORT":      ["patient_name", "lab_name", "tests", "sample_date"],
    "PHARMACY_BILL":   ["pharmacy_name", "total_amount", "medicines"],
    "DENTAL_REPORT":   ["patient_name", "hospital_name", "total_amount"],
    "DIAGNOSTIC_REPORT": ["patient_name", "hospital_name", "tests"],
    "DISCHARGE_SUMMARY": ["patient_name", "hospital_name", "diagnosis"],
}

_PROMPTS: dict[str, str] = {
    "PRESCRIPTION": (
        "You are extracting data from an Indian medical prescription. "
        "Indian prescriptions are often handwritten, may have rubber stamps, and use medical shorthand. "
        "Extract ALL of the following. If a field is unclear or missing, set it to null — never guess or hallucinate. "
        "Return ONLY valid JSON, no other text:\n"
        '{\n'
        '  "patient_name": "full name as written",\n'
        '  "patient_age": integer or null,\n'
        '  "patient_gender": "M" or "F" or null,\n'
        '  "doctor_name": "Dr. full name",\n'
        '  "doctor_registration": "state/number/year format e.g. KA/45678/2015",\n'
        '  "doctor_specialization": "specialty or null",\n'
        '  "hospital_name": "clinic or hospital name",\n'
        '  "diagnosis": ["primary diagnosis", "secondary if any"],\n'
        '  "medicines": ["Medicine name dosage duration"],\n'
        '  "treatment_date": "YYYY-MM-DD or null",\n'
        '  "confidence_notes": ["note any fields that were hard to read"]\n'
        '}'
    ),
    "HOSPITAL_BILL": (
        "You are extracting data from an Indian hospital or clinic bill. "
        "Bills may be handwritten, have corrections, or use abbreviations. "
        "Return ONLY valid JSON:\n"
        '{\n'
        '  "patient_name": "name as written",\n'
        '  "patient_age": integer or null,\n'
        '  "hospital_name": "full hospital/clinic name",\n'
        '  "hospital_address": "address if visible",\n'
        '  "bill_date": "YYYY-MM-DD or null",\n'
        '  "bill_number": "bill/invoice number or null",\n'
        '  "line_items": [{"description": "item name", "amount": float, "quantity": int or null}],\n'
        '  "total_amount": float or null,\n'
        '  "doctor_name": "referring doctor or null",\n'
        '  "confidence_notes": ["fields that were unclear"]\n'
        '}'
    ),
    "LAB_REPORT": (
        "You are extracting data from an Indian diagnostic lab report. "
        "Return ONLY valid JSON:\n"
        '{\n'
        '  "patient_name": "name as written",\n'
        '  "patient_age": integer or null,\n'
        '  "lab_name": "laboratory name",\n'
        '  "referring_doctor": "doctor name or null",\n'
        '  "sample_date": "YYYY-MM-DD or null",\n'
        '  "report_date": "YYYY-MM-DD or null",\n'
        '  "tests": [{"test_name": "name", "result": "value", "unit": "unit or null", '
        '"normal_range": "range or null", "abnormal": boolean}],\n'
        '  "diagnosis_impression": "pathologist remarks or null",\n'
        '  "total_amount": null,\n'
        '  "confidence_notes": []\n'
        '}'
    ),
    "PHARMACY_BILL": (
        "You are extracting data from an Indian pharmacy bill. "
        "Return ONLY valid JSON:\n"
        '{\n'
        '  "patient_name": "name or null",\n'
        '  "pharmacy_name": "pharmacy name",\n'
        '  "drug_license": "license number or null",\n'
        '  "bill_date": "YYYY-MM-DD or null",\n'
        '  "doctor_name": "prescribing doctor or null",\n'
        '  "medicines": [{"name": "medicine name and strength", "quantity": int or null, '
        '"mrp": float or null, "amount": float}],\n'
        '  "subtotal": float or null,\n'
        '  "discount": float or null,\n'
        '  "total_amount": float,\n'
        '  "confidence_notes": []\n'
        '}'
    ),
}

# Fall back to HOSPITAL_BILL prompt for other types
_PROMPTS["DENTAL_REPORT"]       = _PROMPTS["HOSPITAL_BILL"]
_PROMPTS["DIAGNOSTIC_REPORT"]   = _PROMPTS["LAB_REPORT"]
_PROMPTS["DISCHARGE_SUMMARY"]   = _PROMPTS["HOSPITAL_BILL"]
_PROMPTS["UNKNOWN"]             = _PROMPTS["HOSPITAL_BILL"]


def _detect_media_type(filename: str, data: bytes) -> str:
    """Guess MIME type from filename extension or first bytes (magic)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("jpg", "jpeg"):
        return "image/jpeg"
    if ext == "png":
        return "image/png"
    if ext == "gif":
        return "image/gif"
    if ext == "webp":
        return "image/webp"
    if ext == "pdf":
        return "application/pdf"
    # Sniff magic bytes
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:2] in (b"\xff\xd8", b"\xff\xe0", b"\xff\xe1"):
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"  # safe default


class DocumentParsingAgent:
    """
    Parses uploaded claim documents with Claude Vision.

    Uses claude-opus-4-5 for production parsing.
    Falls back to parse_mock() when no Anthropic client is provided.
    """

    def __init__(self, anthropic_client=None) -> None:
        self.client = anthropic_client
        self.model = "claude-opus-4-5"

    # ------------------------------------------------------------------
    # Public: real parsing
    # ------------------------------------------------------------------

    async def parse(
        self,
        document_bytes: bytes,
        document_type: DocumentType,
        filename: str,
    ) -> DocumentParsingResult:
        """Extract structured data from a medical document using Claude Vision."""
        if self.client is None:
            logger.info("No Anthropic client; returning mock for %s", filename)
            return self.parse_mock(document_type=document_type)

        b64_data = base64.standard_b64encode(document_bytes).decode("utf-8")
        media_type = _detect_media_type(filename, document_bytes)
        prompt = _PROMPTS.get(document_type.value, _PROMPTS["HOSPITAL_BILL"])

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_data,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            raw_text = response.content[0].text
            extracted = self._parse_json_response(raw_text)

            if extracted is None:
                return DocumentParsingResult(
                    document_type=document_type,
                    filename=filename,
                    parsing_status="PARTIAL",
                    error_message="Could not parse JSON from model response",
                    overall_confidence=0.3,
                    extraction_warnings=["JSON parsing failed; partial data may be unavailable"],
                )

            result = self._map_to_result(extracted, document_type, filename)
            confidence, low_fields = self._calculate_confidence(extracted, document_type)
            result.overall_confidence = confidence
            result.low_confidence_fields = low_fields
            return result

        except Exception as exc:
            logger.error("DocumentParsingAgent.parse failed for %s: %s", filename, exc)
            return DocumentParsingResult(
                document_type=document_type,
                filename=filename,
                parsing_status="FAILED",
                error_message=str(exc),
                overall_confidence=0.0,
            )

    # ------------------------------------------------------------------
    # Public: mock parsing for testing / no-bytes fallback
    # ------------------------------------------------------------------

    def parse_mock(
        self,
        document_type: DocumentType,
        member_name: str = "Rajesh Kumar",
        amount: float = 1500.0,
        diagnosis: Optional[list[str]] = None,
        hospital_name: Optional[str] = None,
        doctor_name: Optional[str] = None,
        line_items: Optional[list[dict]] = None,
        patient_name: Optional[str] = None,
        treatment_items: Optional[list[str]] = None,
        parsing_status: str = "SUCCESS",
        error_message: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> DocumentParsingResult:
        """Return realistic Indian medical data for testing the pipeline end-to-end."""
        _diagnosis = diagnosis or ["Viral Fever"]
        _patient  = patient_name or member_name
        _hospital = hospital_name or "City Clinic, Bengaluru"
        _doctor   = doctor_name   or "Dr. Arun Sharma"

        if document_type == DocumentType.PRESCRIPTION:
            return DocumentParsingResult(
                document_type=DocumentType.PRESCRIPTION,
                filename="prescription.jpg",
                patient_name=_patient,
                patient_age=35,
                patient_gender="M",
                doctor_name=_doctor,
                doctor_registration="KA/45678/2015",
                doctor_specialization="General Medicine",
                hospital_name=_hospital,
                diagnosis=_diagnosis,
                treatment_items=treatment_items or [],
                medicines=["Paracetamol 650mg", "Vitamin C 500mg"],
                treatment_date=datetime.utcnow().strftime("%Y-%m-%d"),
                overall_confidence=confidence if confidence is not None else 0.92,
                parsing_status=parsing_status,  # type: ignore[arg-type]
                error_message=error_message,
            )

        if document_type == DocumentType.HOSPITAL_BILL:
            _items = (
                [ExtractedLineItem(**i) if isinstance(i, dict) else i for i in line_items]
                if line_items
                else [ExtractedLineItem(description="Consultation Fee", amount=amount)]
            )
            return DocumentParsingResult(
                document_type=DocumentType.HOSPITAL_BILL,
                filename="hospital_bill.jpg",
                patient_name=_patient,
                hospital_name=_hospital,
                bill_date=datetime.utcnow().strftime("%Y-%m-%d"),
                total_amount=amount,
                line_items=_items,
                overall_confidence=confidence if confidence is not None else 0.90,
                parsing_status=parsing_status,  # type: ignore[arg-type]
                error_message=error_message,
            )

        if document_type == DocumentType.LAB_REPORT:
            return DocumentParsingResult(
                document_type=DocumentType.LAB_REPORT,
                filename="lab_report.jpg",
                patient_name=_patient,
                hospital_name=hospital_name or "City Diagnostics Lab",
                treatment_items=treatment_items or [],
                overall_confidence=confidence if confidence is not None else 0.88,
                parsing_status=parsing_status,  # type: ignore[arg-type]
                error_message=error_message,
            )

        if document_type == DocumentType.PHARMACY_BILL:
            return DocumentParsingResult(
                document_type=DocumentType.PHARMACY_BILL,
                filename="pharmacy_bill.jpg",
                patient_name=_patient,
                hospital_name=hospital_name or "Apollo Pharmacy",
                medicines=["Paracetamol 650mg", "Vitamin C 500mg"],
                total_amount=amount,
                overall_confidence=confidence if confidence is not None else 0.89,
                parsing_status=parsing_status,  # type: ignore[arg-type]
                error_message=error_message,
            )

        # Generic fallback for other types
        return DocumentParsingResult(
            document_type=document_type,
            filename=f"{document_type.value.lower()}.jpg",
            patient_name=_patient,
            hospital_name=_hospital,
            total_amount=amount,
            overall_confidence=confidence if confidence is not None else 0.85,
            parsing_status=parsing_status,  # type: ignore[arg-type]
            error_message=error_message,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_json_response(self, text: str) -> Optional[dict]:
        """Extract JSON from Claude response, tolerating extra prose."""
        text = text.strip()
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find a JSON block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    def _calculate_confidence(
        self, extracted: dict, document_type: DocumentType
    ) -> tuple[float, list[str]]:
        """
        Score based on critical-field coverage.
        Full score = 1.0 when all critical fields are present.
        Deduct 0.1 per confidence_note. Floor 0.0, ceil 1.0.
        """
        critical = _CRITICAL_FIELDS.get(document_type.value, [])
        if not critical:
            return 0.85, []

        found = 0
        low_fields: list[str] = []
        for field in critical:
            val = extracted.get(field)
            if val is not None and val != "" and val != [] and val != {}:
                found += 1
            else:
                low_fields.append(field)

        score = found / len(critical)
        notes = extracted.get("confidence_notes", [])
        score -= 0.1 * len(notes)
        score = round(max(0.0, min(1.0, score)), 4)
        return score, low_fields

    def _map_to_result(
        self, extracted: dict, document_type: DocumentType, filename: str
    ) -> DocumentParsingResult:
        """Map raw extracted dict to a typed DocumentParsingResult."""
        notes = extracted.get("confidence_notes", [])

        # Build line_items for bill types
        raw_items = extracted.get("line_items", [])
        line_items: list[ExtractedLineItem] = []
        for item in raw_items:
            try:
                line_items.append(
                    ExtractedLineItem(
                        description=str(item.get("description", "")),
                        amount=float(item.get("amount", 0)),
                        quantity=item.get("quantity"),
                    )
                )
            except (TypeError, ValueError):
                pass

        # Normalise diagnosis to list
        raw_diag = extracted.get("diagnosis", [])
        if isinstance(raw_diag, str):
            diagnosis = [raw_diag] if raw_diag else []
        else:
            diagnosis = [str(d) for d in raw_diag if d]

        # Normalise medicines to strings
        raw_meds = extracted.get("medicines", [])
        medicines: list[str] = []
        for m in raw_meds:
            if isinstance(m, dict):
                medicines.append(m.get("name", str(m)))
            else:
                medicines.append(str(m))

        # Hospital/lab name — try multiple keys
        hospital = (
            extracted.get("hospital_name")
            or extracted.get("lab_name")
            or extracted.get("pharmacy_name")
            or ""
        )

        return DocumentParsingResult(
            document_type=document_type,
            filename=filename,
            patient_name=extracted.get("patient_name"),
            patient_age=extracted.get("patient_age"),
            patient_gender=extracted.get("patient_gender"),
            doctor_name=extracted.get("doctor_name") or extracted.get("referring_doctor"),
            doctor_registration=extracted.get("doctor_registration"),
            doctor_specialization=extracted.get("doctor_specialization"),
            hospital_name=hospital or None,
            hospital_address=extracted.get("hospital_address"),
            diagnosis=diagnosis,
            medicines=medicines,
            total_amount=extracted.get("total_amount"),
            line_items=line_items,
            treatment_date=extracted.get("treatment_date") or extracted.get("sample_date"),
            bill_date=extracted.get("bill_date") or extracted.get("report_date"),
            parsing_notes=notes,
            parsing_status="SUCCESS" if not notes else "PARTIAL",
        )
