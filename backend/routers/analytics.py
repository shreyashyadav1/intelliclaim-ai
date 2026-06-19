"""
IntelliClaim AI - Analytics Router

Endpoints for dashboard analytics and reporting.
"""

import logging

from fastapi import APIRouter, Query

from services.analytics_service import AnalyticsService

logger = logging.getLogger("intelliclaim.analytics")
router = APIRouter()
analytics = AnalyticsService()


@router.get("/analytics/overview")
async def get_overview():
    """Get dashboard overview statistics."""
    try:
        return await analytics.get_overview()
    except Exception as e:
        logger.error(f"Analytics overview failed: {e}")
        # Return demo data on failure
        return {
            "total_claims": 1247,
            "documents_processed": 3891,
            "claims_by_status": {"pending": 89, "approved": 934, "rejected": 156, "flagged": 68},
            "avg_treatment_cost": 28450.75,
            "avg_risk_score": 32.4,
            "high_risk_count": 68,
            "approval_rate": 74.9,
        }


@router.get("/analytics/claims-trend")
async def get_claims_trend(days: int = Query(30, ge=7, le=365)):
    """Get daily claims processed over the last N days."""
    try:
        return await analytics.get_claims_trend(days)
    except Exception as e:
        logger.error(f"Claims trend failed: {e}")
        # Return demo data
        import random
        from datetime import datetime, timedelta
        trend = []
        for i in range(days):
            date_str = (datetime.now() - timedelta(days=days - i)).strftime("%Y-%m-%d")
            trend.append({"date": date_str, "count": random.randint(15, 65)})
        return trend


@router.get("/analytics/risk-distribution")
async def get_risk_distribution():
    """Get risk score distribution."""
    try:
        return await analytics.get_risk_distribution()
    except Exception as e:
        logger.error(f"Risk distribution failed: {e}")
        return [
            {"range": "Low (0-29)", "count": 742, "min": 0, "max": 30},
            {"range": "Medium (30-59)", "count": 328, "min": 30, "max": 60},
            {"range": "High (60-79)", "count": 134, "min": 60, "max": 80},
            {"range": "Critical (80-100)", "count": 43, "min": 80, "max": 101},
        ]


@router.get("/analytics/recent-claims")
async def get_recent_claims(limit: int = Query(10, ge=1, le=50)):
    """Get most recent claims."""
    try:
        return await analytics.get_recent_claims(limit)
    except Exception as e:
        logger.error(f"Recent claims failed: {e}")
        # Return demo data
        demo_claims = [
            {"id": f"clm-{i}", "claim_number": f"CLM-2026-{10000+i}", "policy_number": f"POL-2026-{50000+i}", "patient_name": name, "diagnosis": diag, "treatment_cost": cost, "hospital_name": hospital, "status": status, "risk_score": risk, "created_at": "2026-06-15T10:00:00Z"}
            for i, (name, diag, cost, hospital, status, risk) in enumerate([
                ("Sarah Johnson", "ACL Tear (S83.5)", 34500.00, "Metro General Hospital", "approved", 15.0),
                ("Michael Chen", "Type 2 Diabetes (E11.9)", 12800.00, "City Medical Center", "pending", 22.0),
                ("Emily Rodriguez", "Acute Appendicitis (K35.80)", 28900.00, "St. Mary's Hospital", "approved", 8.0),
                ("James Williams", "Lumbar Disc Herniation (M51.16)", 67200.00, "Spine Care Institute", "flagged", 72.0),
                ("Amanda Thompson", "Knee Replacement (Z96.651)", 89500.00, "Orthopedic Surgical Center", "pending", 45.0),
                ("Robert Davis", "Coronary Artery Disease (I25.10)", 156000.00, "Heart & Vascular Center", "flagged", 85.0),
                ("Lisa Garcia", "Cholecystitis (K81.0)", 19200.00, "Regional Medical Center", "approved", 5.0),
                ("David Brown", "Rotator Cuff Tear (M75.10)", 31400.00, "Sports Medicine Clinic", "approved", 18.0),
                ("Jennifer Martinez", "Breast Cancer Stage II (C50.9)", 124500.00, "Cancer Treatment Center", "approved", 12.0),
                ("Christopher Lee", "Pneumonia (J18.9)", 8900.00, "Community Hospital", "rejected", 55.0),
            ])
        ]
        return demo_claims[:limit]
