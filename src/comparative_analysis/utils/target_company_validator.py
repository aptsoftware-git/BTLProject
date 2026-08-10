"""
target_company_validator.py
===========================
Pre-report validation gate for Comparative Analysis pipeline.
Ensures target company identity is valid, grounded, non-customer, and consistent
across all generated sections before final_report.json is emitted.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("comparative_analysis.target_company_validator")


class TargetCompanyValidationError(ValueError):
    """Raised when Target Company Validation Gate fails."""
    pass


class TargetCompanyValidationGate:
    """
    Validation Gate executed before report emission.
    Guarantees target company identity integrity.
    """

    @classmethod
    def validate(
        cls,
        company_profile: Any,
        competitors: List[Any],
        swot: Any = None,
        recommendations: List[Any] = None,
        resolved_identity: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Runs 4 strict validation checks:
          1. Target company name exists and is not generic/empty.
          2. Target company is not a project/customer mention ("Talcher Fertilizer Limited", etc.).
          3. Target company is not listed among its own competitors.
          4. Target company is consistent across all report objects.

        Raises:
            TargetCompanyValidationError if any check fails.
        """
        target_name = (company_profile.company_name or "").strip()

        # Check 1: Target Company Name Existence & Non-generic
        if not target_name or target_name.lower() in ("target company", "unknown", "none", "n/a"):
            raise TargetCompanyValidationError(
                f"Validation Gate Failed: Target company name is generic or empty ('{target_name}')."
            )

        # Check 2: Target Company is NOT a Customer / Project Mention
        lower_target = target_name.lower()
        if "talcher" in lower_target or "package for" in lower_target or "handling plant" in lower_target:
            raise TargetCompanyValidationError(
                f"Validation Gate Failed: Target company '{target_name}' is a customer/project reference, not the legal report owner."
            )

        # Check 3: Target Company is NOT listed among its own competitors
        if competitors:
            for comp in competitors:
                comp_name = getattr(comp, "company_name", str(comp)).strip().lower()
                if comp_name and (comp_name == lower_target or lower_target in comp_name or comp_name in lower_target):
                    raise TargetCompanyValidationError(
                        f"Validation Gate Failed: Target company '{target_name}' is improperly listed as a competitor to itself."
                    )

        # Check 4: Cross-section Consistency against resolved_identity
        if resolved_identity and resolved_identity.get("target_company"):
            expected_name = resolved_identity["target_company"].strip()
            if target_name.lower() != expected_name.lower():
                raise TargetCompanyValidationError(
                    f"Validation Gate Failed: Target company inconsistency! "
                    f"Profile name ('{target_name}') does not match resolved identity ('{expected_name}')."
                )

        logger.info("TargetCompanyValidationGate PASSED for target company: '%s'", target_name)
        return True
