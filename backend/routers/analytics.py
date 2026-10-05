"""
IntelliClaim AI - Analytics Router

Endpoints for dashboard analytics and reporting. Every number is computed
from MongoDB; if the database is unavailable the request fails (503) rather
than returning placeholder figures.
"""

import logging

from fastapi import APIRouter, Query

from services.analytics_service import analytics_service as analytics

logger = logging.getLogger("intelliclaim.analytics")
router = APIRouter()


@router.get("/analytics/overview")
async def get_overview():
    """Get dashboard overview statistics."""
    return await analytics.get_overview()


@router.get("/analytics/claims-trend")
async def get_claims_trend(days: int = Query(30, ge=7, le=365)):
    """Get daily claims created over the last N days, including today."""
    return await analytics.get_claims_trend(days)


@router.get("/analytics/risk-distribution")
async def get_risk_distribution():
    """Get risk score distribution."""
    return await analytics.get_risk_distribution()


@router.get("/analytics/recent-claims")
async def get_recent_claims(limit: int = Query(10, ge=1, le=50)):
    """Get most recent claims."""
    return await analytics.get_recent_claims(limit)
