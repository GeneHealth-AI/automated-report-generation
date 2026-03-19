import sqlite3
import logging
import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class MutationCache:
    """
    Manages a SQLite database for caching generated mutation descriptions.
    Ensures consistent reporting for identical variants across runs.
    """
    
    def __init__(self, db_path: str = "mutation_cache.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database schema if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS variant_descriptions (
                        signature TEXT PRIMARY KEY,
                        description TEXT NOT NULL,
                        model_version TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize mutation cache database: {e}")
            raise

    def get(self, signature: str) -> Optional[str]:
        """Retrieve a cached description by its signature."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT description FROM variant_descriptions WHERE signature = ?", 
                    (signature,)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Error retrieving from mutation cache: {e}")
        return None

    def set(self, signature: str, description: str, model_version: str = "unknown"):
        """Save a generated description to the cache."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO variant_descriptions (signature, description, model_version, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (signature, description, model_version, datetime.datetime.now())
                )
                conn.commit()
                logger.info(f"Cached description for {signature}")
        except Exception as e:
            logger.error(f"Error caching description for {signature}: {e}")

    def list_signatures(self) -> list[str]:
        """Retrieve all signatures present in the cache."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT signature FROM variant_descriptions")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error listing cache signatures: {e}")
            return []
