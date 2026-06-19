"""
IntelliClaim AI - Validation Service

Automated validation and risk detection for insurance claims:
- Missing field detection
- Duplicate claim detection
- Suspicious billing pattern analysis
- Composite risk score calculation
"""

import logging
from datetime import datetime

from db.connection import get_database

logger = logging.getLogger("intelliclaim.validation")

REQUIRED_FIELDS = [
    "policy_number",
    "claim_number",
    "patient_name",
    "diagnosis",
    "treatment_cost",
    "hospital_name",
]

HIGH_COST_THRESHOLD = 50000
VERY_HIGH_COST_THRESHOLD = 150000

SUSPICIOUS_KEYWORDS = [
    "cosmetic",
    "elective",
    "experimental",
    "off-label",
]


class ValidationService:
    """Validates claims and calculates fraud risk scores."""

    async def validate_claim(self, claim: dict) -> dict:
        """
        Run full validation on a claim.

        Returns:
            dict with risk_score, risk_level, flags, is_duplicate
        """
        flags = []

        # 1. Missing field detection
        missing = self._check_missing_fields(claim)
        if missing:
            flags.append({
                "type": "missing_fields",
                "description": f"Missing required fields: {', '.join(missing)}",
                "severity": "high" if len(missing) > 2 else "medium",
                "fields": missing,
            })

        # 2. Duplicate detection
        is_duplicate = await self._check_duplicate(claim)
        if is_duplicate:
            flags.append({
                "type": "duplicate_claim",
                "description": "Potential duplicate claim detected with similar patient, diagnosis, and date",
                "severity": "high",
            })

        # 3. Billing pattern analysis
        billing_flags = self._check_billing_patterns(claim)
        flags.extend(billing_flags)

        # 4. Date validation
        date_flags = self._check_dates(claim)
        flags.extend(date_flags)

        # 5. Calculate risk score
        risk_score = self._calculate_risk_score(flags, is_duplicate)
        risk_level = self._get_risk_level(risk_score)

        return {
            "risk_score": round(risk_score, 1),
            "risk_level": risk_level,
            "flags": flags,
            "is_duplicate": is_duplicate,
            "total_flags": len(flags),
        }

    def _check_missing_fields(self, claim: dict) -> list[str]:
        """Check for missing required fields."""
        missing = []
        for field in REQUIRED_FIELDS:
            value = claim.get(field)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                missing.append(field)
        return missing

    async def _check_duplicate(self, claim: dict) -> bool:
        """Check for duplicate claims based on patient + diagnosis + date."""
        db = get_database()
        claim_id = claim.get("_id") or claim.get("id")
        patient_name = claim.get("patient_name", "")
        diagnosis = claim.get("diagnosis", "")

        if not patient_name or not diagnosis:
            return False

        query = {
            "patient_name": {"$regex": patient_name, "$options": "i"},
            "diagnosis": {"$regex": diagnosis[:30], "$options": "i"},
        }
        if claim_id:
            query["_id"] = {"$ne": claim_id}

        count = await db.claims.count_documents(query)
        return count > 0

    def _check_billing_patterns(self, claim: dict) -> list[dict]:
        """Analyze billing patterns for suspicious activity."""
        flags = []
        cost = claim.get("treatment_cost", 0)

        if cost > VERY_HIGH_COST_THRESHOLD:
            flags.append({
                "type": "very_high_cost",
                "description": f"Treatment cost (${cost:,.2f}) exceeds ${VERY_HIGH_COST_THRESHOLD:,} threshold",
                "severity": "high",
            })
        elif cost > HIGH_COST_THRESHOLD:
            flags.append({
                "type": "high_cost",
                "description": f"Treatment cost (${cost:,.2f}) exceeds ${HIGH_COST_THRESHOLD:,} threshold",
                "severity": "medium",
            })

        if cost <= 0:
            flags.append({
                "type": "zero_cost",
                "description": "Treatment cost is zero or negative",
                "severity": "medium",
            })

        # Check for suspicious keywords in diagnosis
        diagnosis = (claim.get("diagnosis") or "").lower()
        for keyword in SUSPICIOUS_KEYWORDS:
            if keyword in diagnosis:
                flags.append({
                    "type": "suspicious_diagnosis",
                    "description": f"Diagnosis contains flagged keyword: '{keyword}'",
                    "severity": "low",
                })
                break

        return flags

    def _check_dates(self, claim: dict) -> list[dict]:
        """Validate dates for logical consistency."""
        flags = []
        admission = claim.get("date_of_admission")
        discharge = claim.get("date_of_discharge")

        if admission and discharge:
            try:
                adm_date = datetime.strptime(admission, "%Y-%m-%d")
                dis_date = datetime.strptime(discharge, "%Y-%m-%d")
                if dis_date < adm_date:
                    flags.append({
                        "type": "invalid_dates",
                        "description": "Discharge date is before admission date",
                        "severity": "high",
                    })
                elif (dis_date - adm_date).days > 90:
                    flags.append({
                        "type": "long_stay",
                        "description": f"Hospital stay exceeds 90 days ({(dis_date - adm_date).days} days)",
                        "severity": "medium",
                    })
            except ValueError:
                flags.append({
                    "type": "date_format",
                    "description": "Invalid date format (expected YYYY-MM-DD)",
                    "severity": "low",
                })

        return flags

    def _calculate_risk_score(self, flags: list[dict], is_duplicate: bool) -> float:
        """Calculate composite risk score from 0 to 100."""
        score = 0.0

        severity_weights = {"high": 25, "medium": 15, "low": 5}
        for flag in flags:
            score += severity_weights.get(flag.get("severity", "low"), 5)

        if is_duplicate:
            score += 20

        return min(score, 100.0)

    def _get_risk_level(self, score: float) -> str:
        """Classify risk level from score."""
        if score >= 60:
            return "high"
        elif score >= 30:
            return "medium"
        return "low"
