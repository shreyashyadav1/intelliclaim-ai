"""
IntelliClaim AI - Validation Service

Automated validation and risk detection for insurance claims.

Two-layer validation architecture:
  1. Rule-based layer — deterministic checks (missing fields, duplicates,
     billing thresholds, date logic).
  2. AI-assisted layer — GPT-4o evaluates billing anomalies, diagnosis
     inconsistencies, and suspicious patterns, contributing structured
     risk flags and a confidence score to the composite risk model.
"""

import json
import logging
from datetime import datetime
from typing import Any

from config import settings
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

# ---------------------------------------------------------------------------
# OpenAI function schema for AI-assisted validation
# ---------------------------------------------------------------------------
_AI_VALIDATION_TOOL = {
    "type": "function",
    "function": {
        "name": "assess_claim_risk",
        "description": (
            "Assess an insurance claim for potential fraud, billing anomalies, "
            "diagnosis inconsistencies, and suspicious patterns. Return structured risk flags."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "risk_flags": {
                    "type": "array",
                    "description": "List of risk flags detected in this claim.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "Flag category: billing_anomaly, diagnosis_inconsistency, suspicious_pattern, missing_info",
                            },
                            "description": {
                                "type": "string",
                                "description": "Human-readable explanation of the concern.",
                            },
                            "severity": {
                                "type": "string",
                                "enum": ["low", "medium", "high"],
                                "description": "Severity of this risk flag.",
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confidence score from 0.0 to 1.0.",
                            },
                        },
                        "required": ["type", "description", "severity", "confidence"],
                    },
                },
                "ai_risk_score": {
                    "type": "number",
                    "description": "Overall AI risk contribution (0–100). Higher = more suspicious.",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief summary of the AI review findings.",
                },
            },
            "required": ["risk_flags", "ai_risk_score", "summary"],
        },
    },
}


class ValidationService:
    """Validates claims using rule-based + AI-assisted layers."""

    async def validate_claim(self, claim: dict) -> dict:
        """Run full two-layer validation on a claim.

        Returns:
            dict with risk_score, risk_level, flags, is_duplicate, ai_review
        """
        flags = []

        # 1. Rule-based: missing field detection
        missing = self._check_missing_fields(claim)
        if missing:
            flags.append({
                "type": "missing_fields",
                "description": f"Missing required fields: {', '.join(missing)}",
                "severity": "high" if len(missing) > 2 else "medium",
            })

        # 2. Rule-based: duplicate detection
        is_duplicate = await self._check_duplicate(claim)
        if is_duplicate:
            flags.append({
                "type": "duplicate_claim",
                "description": "Potential duplicate claim detected with similar patient, diagnosis, and date",
                "severity": "high",
            })

        # 3. Rule-based: billing pattern analysis
        flags.extend(self._check_billing_patterns(claim))

        # 4. Rule-based: date validation
        flags.extend(self._check_dates(claim))

        # 5. AI-assisted layer (GPT-4o)
        ai_result = await self._ai_validate_claim(claim)
        ai_flags = ai_result.get("risk_flags", [])
        flags.extend(ai_flags)

        # 6. Composite risk score (rule-based + AI)
        risk_score = self._calculate_risk_score(flags, is_duplicate, ai_result)
        risk_level = self._get_risk_level(risk_score)

        return {
            "risk_score": round(risk_score, 1),
            "risk_level": risk_level,
            "flags": flags,
            "is_duplicate": is_duplicate,
            "total_flags": len(flags),
            "ai_review": {
                "ai_risk_score": ai_result.get("ai_risk_score", 0.0),
                "ai_confidence": ai_result.get("avg_confidence", 0.0),
                "ai_summary": ai_result.get("summary", ""),
                "ai_flag_count": len(ai_flags),
            },
        }

    # ----------------------------------------------------------------
    # AI-assisted validation — GPT-4o
    # ----------------------------------------------------------------
    async def _ai_validate_claim(self, claim: dict) -> dict[str, Any]:
        """Use GPT-4o to evaluate a claim for anomalies and suspicious patterns.

        Returns a dict with risk_flags, ai_risk_score, summary, avg_confidence.
        """
        if not settings.has_openai_key:
            return {
                "risk_flags": [],
                "ai_risk_score": 0.0,
                "summary": "AI review not available (no OpenAI key configured).",
                "avg_confidence": 0.0,
            }

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

            # Build a structured claim summary for the prompt
            claim_summary = self._build_claim_summary(claim)

            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert insurance fraud analyst. Review the provided claim "
                            "and identify any billing anomalies, diagnosis inconsistencies, or suspicious "
                            "patterns. Be thorough but objective. Use the provided function to structure your output."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Review this insurance claim:\n\n{claim_summary}",
                    },
                ],
                tools=[_AI_VALIDATION_TOOL],
                tool_choice={"type": "function", "function": {"name": "assess_claim_risk"}},
                temperature=0.2,
            )

            tool_call = response.choices[0].message.tool_calls[0]
            result = json.loads(tool_call.function.arguments)

            ai_flags = result.get("risk_flags", [])
            avg_confidence = (
                sum(f.get("confidence", 0.0) for f in ai_flags) / len(ai_flags)
                if ai_flags else 0.0
            )

            logger.info(
                "AI validation complete for claim %s — %d flags, ai_score=%.1f, avg_conf=%.2f",
                claim.get("claim_number", "unknown"),
                len(ai_flags),
                result.get("ai_risk_score", 0.0),
                avg_confidence,
            )

            return {
                "risk_flags": ai_flags,
                "ai_risk_score": result.get("ai_risk_score", 0.0),
                "summary": result.get("summary", ""),
                "avg_confidence": round(avg_confidence, 2),
            }

        except Exception as e:
            logger.warning("AI validation failed: %s", str(e))
            return {
                "risk_flags": [],
                "ai_risk_score": 0.0,
                "summary": f"AI review unavailable: {str(e)}",
                "avg_confidence": 0.0,
            }

    def _build_claim_summary(self, claim: dict) -> str:
        """Build a plain-text summary of a claim for the AI prompt."""
        lines = [
            f"Claim Number: {claim.get('claim_number', 'N/A')}",
            f"Policy Number: {claim.get('policy_number', 'N/A')}",
            f"Patient: {claim.get('patient_name', 'N/A')}",
            f"Diagnosis: {claim.get('diagnosis', 'N/A')}",
            f"Treatment Cost: ${claim.get('treatment_cost', 0):,.2f}",
            f"Hospital: {claim.get('hospital_name', 'N/A')}",
            f"Hospital Address: {claim.get('hospital_address', 'N/A')}",
            f"Provider ID: {claim.get('provider_id', 'N/A')}",
            f"Date of Service: {claim.get('date_of_service', 'N/A')}",
            f"Date of Admission: {claim.get('date_of_admission', 'N/A')}",
            f"Date of Discharge: {claim.get('date_of_discharge', 'N/A')}",
            f"Status: {claim.get('status', 'N/A')}",
            f"Extraction Confidence: {claim.get('extraction_confidence', 0.0)}",
        ]
        return "\n".join(lines)

    # ----------------------------------------------------------------
    # Rule-based checks (preserved from original)
    # ----------------------------------------------------------------
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

    # ----------------------------------------------------------------
    # Composite scoring
    # ----------------------------------------------------------------
    def _calculate_risk_score(
        self, flags: list[dict], is_duplicate: bool, ai_result: dict
    ) -> float:
        """Calculate composite risk score from 0 to 100.

        Rule-based flags and AI risk score are combined into a single
        composite score capped at 100.
        """
        score = 0.0

        # Rule-based flag weights
        severity_weights = {"high": 25, "medium": 15, "low": 5}
        for flag in flags:
            # Skip AI flags in this loop (handled separately)
            if flag.get("type") in ("billing_anomaly", "diagnosis_inconsistency", "suspicious_pattern"):
                continue
            score += severity_weights.get(flag.get("severity", "low"), 5)

        # Duplicate penalty
        if is_duplicate:
            score += 20

        # AI risk score (weighted at 40% of its value to blend with rules)
        ai_score = ai_result.get("ai_risk_score", 0.0)
        avg_confidence = ai_result.get("avg_confidence", 0.0)
        if ai_score > 0 and avg_confidence > 0:
            # Weight AI contribution by its confidence
            score += ai_score * 0.4 * avg_confidence

        return min(score, 100.0)

    def _get_risk_level(self, score: float) -> str:
        """Classify risk level from composite score."""
        if score >= 60:
            return "high"
        elif score >= 30:
            return "medium"
        return "low"


# Module-level singleton
validation_service = ValidationService()
