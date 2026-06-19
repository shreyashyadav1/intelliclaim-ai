"""
IntelliClaim AI - Analytics Service

MongoDB aggregation pipelines for dashboard analytics:
- Overview stats
- Claims trend over time
- Risk score distribution
- Recent claims
"""

import logging
from datetime import datetime, timedelta, timezone

from db.connection import get_database

logger = logging.getLogger("intelliclaim.analytics")


class AnalyticsService:
    """Provides aggregated analytics for the dashboard."""

    async def get_overview(self) -> dict:
        """Get dashboard overview statistics."""
        db = get_database()

        total_claims = await db.claims.count_documents({})
        total_documents = await db.documents.count_documents({})

        # Claims by status
        status_pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        status_cursor = db.claims.aggregate(status_pipeline)
        status_results = await status_cursor.to_list(length=10)
        claims_by_status = {r["_id"]: r["count"] for r in status_results}

        # Average treatment cost
        avg_pipeline = [
            {"$group": {"_id": None, "avg_cost": {"$avg": "$treatment_cost"}, "avg_risk": {"$avg": "$risk_score"}}}
        ]
        avg_cursor = db.claims.aggregate(avg_pipeline)
        avg_results = await avg_cursor.to_list(length=1)
        avg_cost = avg_results[0]["avg_cost"] if avg_results else 0
        avg_risk = avg_results[0]["avg_risk"] if avg_results else 0

        # High risk count
        high_risk_count = await db.claims.count_documents({"risk_score": {"$gte": 60}})

        # Approved rate
        approved_count = claims_by_status.get("approved", 0)
        approval_rate = (approved_count / total_claims * 100) if total_claims > 0 else 0

        return {
            "total_claims": total_claims,
            "documents_processed": total_documents,
            "claims_by_status": claims_by_status,
            "avg_treatment_cost": round(avg_cost, 2),
            "avg_risk_score": round(avg_risk, 1),
            "high_risk_count": high_risk_count,
            "approval_rate": round(approval_rate, 1),
        }

    async def get_claims_trend(self, days: int = 30) -> list[dict]:
        """Get daily claims count over the last N days."""
        db = get_database()
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        pipeline = [
            {"$match": {"created_at": {"$gte": start_date}}},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]

        cursor = db.claims.aggregate(pipeline)
        results = await cursor.to_list(length=days)

        # Fill in missing dates with 0
        trend = []
        current = start_date
        result_map = {r["_id"]: r["count"] for r in results}
        for i in range(days):
            date_str = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            trend.append({"date": date_str, "count": result_map.get(date_str, 0)})

        return trend

    async def get_risk_distribution(self) -> list[dict]:
        """Get risk score distribution in ranges."""
        db = get_database()

        ranges = [
            {"label": "Low (0-29)", "min": 0, "max": 30},
            {"label": "Medium (30-59)", "min": 30, "max": 60},
            {"label": "High (60-79)", "min": 60, "max": 80},
            {"label": "Critical (80-100)", "min": 80, "max": 101},
        ]

        distribution = []
        for r in ranges:
            count = await db.claims.count_documents({
                "risk_score": {"$gte": r["min"], "$lt": r["max"]}
            })
            distribution.append({
                "range": r["label"],
                "count": count,
                "min": r["min"],
                "max": r["max"],
            })

        return distribution

    async def get_recent_claims(self, limit: int = 10) -> list[dict]:
        """Get the most recent claims."""
        db = get_database()
        cursor = db.claims.find().sort("created_at", -1).limit(limit)
        claims = await cursor.to_list(length=limit)

        for claim in claims:
            claim["id"] = claim.pop("_id")

        return claims
