"""
IntelliClaim AI - MongoDB Connection Management

Provides async MongoDB connectivity via Motor, including lifecycle
hooks for FastAPI startup/shutdown and index creation.
"""

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import settings

logger = logging.getLogger(__name__)

# Module-level connection state
_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None


def get_database() -> AsyncIOMotorDatabase:
    """Return the active Motor database instance.

    Raises:
        RuntimeError: If called before connect_db().
    """
    if _database is None:
        raise RuntimeError(
            "Database not initialised. Call connect_db() during app startup."
        )
    return _database


async def connect_db() -> None:
    """Establish the MongoDB connection and create required indexes.

    This should be called once during FastAPI's startup event.
    """
    global _client, _database

    logger.info("Connecting to MongoDB at %s …", settings.MONGODB_URI)
    _client = AsyncIOMotorClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=5000,
    )
    _database = _client[settings.MONGODB_DB_NAME]

    # Verify connectivity
    try:
        await _client.admin.command("ping")
        logger.info("MongoDB connection established — database: %s", settings.MONGODB_DB_NAME)
    except Exception as e:
        logger.warning(
            "MongoDB ping failed (%s). The app will still start but DB "
            "operations will fail until MongoDB is reachable.",
            str(e),
        )

    # Create indexes
    await _create_indexes()


async def _create_indexes() -> None:
    """Create indexes on the claims and documents collections."""
    try:
        db = get_database()

        # Claims indexes
        claims = db["claims"]
        await claims.create_index("claim_number", unique=True, sparse=True)
        await claims.create_index("policy_number")
        await claims.create_index("status")
        await claims.create_index("risk_score")
        await claims.create_index("created_at")

        # Documents indexes
        documents = db["documents"]
        await documents.create_index("claim_id")
        await documents.create_index("processing_status")
        await documents.create_index("created_at")

        logger.info("MongoDB indexes created successfully")
    except Exception as e:
        logger.warning("Failed to create indexes: %s", str(e))


async def close_db() -> None:
    """Close the MongoDB connection gracefully.

    This should be called during FastAPI's shutdown event.
    """
    global _client, _database

    if _client is not None:
        _client.close()
        logger.info("MongoDB connection closed")
        _client = None
        _database = None
