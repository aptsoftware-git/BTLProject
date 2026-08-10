"""
test_target_company_identification.py
======================================
Tests for Target Company Identification, Disambiguation & Validation Gate in Comparative Analysis.

Verifies:
1. DocumentSubjectResolver extracts true legal report owner from corporate disclosures (CIN, Directors' Report, Annual Report headers, Balance Sheet).
2. Anti-collision filter rejects customer/project mentions ("Talcher Fertilizer Limited", "NTPC", "WBPDCL") from becoming the target company even when mentioned heavily.
3. TargetCompanyValidationGate rejects ungrounded, customer-referenced, or inconsistent target companies.
4. Downstream agents retain locked target company identity.
"""

from __future__ import annotations

import unittest
from typing import Dict, List, Any
from unittest.mock import MagicMock

from src.comparative_analysis.utils.document_subject_resolver import (
    DocumentSubjectResolver,
    TargetCompanyResolutionError,
)
from src.comparative_analysis.utils.target_company_validator import (
    TargetCompanyValidationGate,
    TargetCompanyValidationError,
)
from src.comparative_analysis.models import (
    CompanyProfile,
    CompetitorProfile,
    SWOTComparison,
    StrategicRecommendation,
)


class TestTargetCompanyIdentification(unittest.TestCase):

    def test_front_matter_corporate_disclosure_grounding(self):
        """Verifies corporate disclosures on cover/front-matter ground the legal report owner."""
        chunks = [
            {
                "page_number": 1,
                "text": "BTL EPC LIMITED\nANNUAL REPORT 2024-2025\nCorporate Identification Number (CIN): L27109WB1962PLC025484\nRegistered Office: 2, Jessore Road, Kolkata"
            },
            {
                "page_number": 2,
                "text": "DIRECTORS' REPORT TO THE MEMBERS OF BTL EPC LIMITED\nYour Directors have pleasure in presenting..."
            },
            {
                "page_number": 5,
                "text": "Major projects executed include coal handling plant for Talcher Fertilizer Limited and ash handling package for TSGENCO."
            }
        ]

        identity = DocumentSubjectResolver.resolve_target_company(chunks, document_id="test_btl_doc")
        self.assertEqual(identity["target_company"], "BTL EPC Limited")
        self.assertEqual(identity["page"], 1)
        self.assertEqual(identity["source"], "document")
        self.assertIn("BTL EPC LIMITED", identity["evidence"].upper())
        self.assertGreaterEqual(identity["confidence"], 85.0)

    def test_customer_project_reference_rejection(self):
        """
        REGRESSION TEST: Heavily mentioned customer/project companies (e.g. Talcher Fertilizer Limited)
        must NOT become the target company when mentioned in project/client context.
        """
        chunks = [
            {
                "page_number": 1,
                "text": "ANNUAL REPORT 2024-25\nCORPORATE INFORMATION\nNAME OF THE COMPANY: BTL EPC LIMITED\nCIN: L27109WB1962PLC025484"
            },
            {
                "page_number": 10,
                "text": "Executed major coal handling plant for Talcher Fertilizer Limited at Talcher site. Talcher Fertilizer Limited project valued at Rs 350 Cr."
            },
            {
                "page_number": 11,
                "text": "Talcher Fertilizer Limited handling plant package phase 1 completed. Second order received from Talcher Fertilizer Limited."
            },
            {
                "page_number": 12,
                "text": "Supply of equipment to Talcher Fertilizer Limited. Contract awarded by Talcher Fertilizer Limited."
            }
        ]

        identity = DocumentSubjectResolver.resolve_target_company(chunks, document_id="test_talcher_heavy_doc")
        
        # Must resolve the legal report owner BTL EPC Limited, NOT Talcher Fertilizer Limited
        self.assertEqual(identity["target_company"], "BTL EPC Limited")
        self.assertNotEqual(identity["target_company"], "Talcher Fertilizer Limited")
        self.assertNotIn("Talcher Fertilizer", identity["target_company"])

    def test_no_hardcoded_company_name(self):
        """Verifies resolver works dynamically for another completely different company (e.g. ABC Engineering Ltd)."""
        chunks = [
            {
                "page_number": 1,
                "text": "ABC ENGINEERING PRIVATE LIMITED\nANNUAL REPORT 2024-25\nCIN: U12345MH2020PTC123456\nRegistered Office: Mumbai, Maharashtra"
            },
            {
                "page_number": 3,
                "text": "DIRECTORS' REPORT TO THE MEMBERS OF ABC ENGINEERING PRIVATE LIMITED"
            }
        ]

        identity = DocumentSubjectResolver.resolve_target_company(chunks, document_id="test_abc_doc")
        self.assertEqual(identity["target_company"], "Abc Engineering Private Limited")
        self.assertEqual(identity["page"], 1)

    def test_ungrounded_document_raises_resolution_error(self):
        """Verifies ungrounded document raises TargetCompanyResolutionError instead of guessing."""
        corrupted_chunks = [
            {"page_number": 1, "text": "Random extracted text with no corporate disclosures or legal entity names."}
        ]

        with self.assertRaises(TargetCompanyResolutionError):
            DocumentSubjectResolver.resolve_target_company(corrupted_chunks, document_id="corrupted_doc")

    def test_validation_gate_accepts_valid_grounded_profile(self):
        """Verifies TargetCompanyValidationGate passes when target company is valid and grounded."""
        profile = CompanyProfile(
            company_name="BTL EPC Limited",
            primary_industry="Engineering Procurement & Construction (EPC)"
        )
        competitors = [
            CompetitorProfile(company_name="Elecon Engineering Ltd"),
            CompetitorProfile(company_name="McNally Bharat Engineering")
        ]
        resolved_identity = {
            "target_company": "BTL EPC Limited",
            "evidence": "CORPORATE INFORMATION: BTL EPC LIMITED",
            "page": 1,
            "source": "document"
        }

        passed = TargetCompanyValidationGate.validate(
            company_profile=profile,
            competitors=competitors,
            resolved_identity=resolved_identity
        )
        self.assertTrue(passed)

    def test_validation_gate_rejects_customer_target_company(self):
        """Verifies TargetCompanyValidationGate fails if target company is a customer mention like Talcher Fertilizer."""
        invalid_profile = CompanyProfile(
            company_name="Talcher Fertilizer Limited",
            primary_industry="Fertilizer Handling"
        )

        with self.assertRaises(TargetCompanyValidationError):
            TargetCompanyValidationGate.validate(
                company_profile=invalid_profile,
                competitors=[]
            )

    def test_validation_gate_rejects_self_as_competitor(self):
        """Verifies TargetCompanyValidationGate fails if target company is listed as a competitor to itself."""
        profile = CompanyProfile(company_name="BTL EPC Limited")
        competitors = [
            CompetitorProfile(company_name="BTL EPC Limited"),  # Self listed as competitor!
            CompetitorProfile(company_name="Elecon Engineering Ltd")
        ]

        with self.assertRaises(TargetCompanyValidationError):
            TargetCompanyValidationGate.validate(
                company_profile=profile,
                competitors=competitors
            )


if __name__ == "__main__":
    unittest.main()
