"""
Job Store Service
SQLite-backed persistence for jobs and clips.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import aiosqlite

from ..config import get_settings
from ..models.clip import Clip
from ..models.job import Job
from ..utils.logger import get_logger

logger = get_logger()


class JobStore:
    """Persistent storage for jobs and clips."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database schema."""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS clips (
                        id TEXT PRIMARY KEY,
                        job_id TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_clips_job_id ON clips(job_id)"
                )
                await conn.commit()

            self._initialized = True
            logger.info(f"Job store initialized at {self.db_path}")

    @staticmethod
    def _to_json(model) -> str:
        if hasattr(model, "model_dump"):
            data = model.model_dump(mode="json")
        else:
            data = model.dict()
        return json.dumps(data, ensure_ascii=False)

    async def upsert_job(self, job: Job):
        """Insert or update a job record."""
        await self.initialize()
        payload = self._to_json(job)
        updated_at = job.updated_at.isoformat()

        async with self._write_lock:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    """
                    INSERT INTO jobs (id, payload, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (job.id, payload, updated_at),
                )
                await conn.commit()

    async def upsert_clip(self, clip: Clip):
        """Insert or update a clip record."""
        await self.initialize()
        payload = self._to_json(clip)
        updated_at = datetime.utcnow().isoformat()

        async with self._write_lock:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    """
                    INSERT INTO clips (id, job_id, payload, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (clip.id, clip.job_id, payload, updated_at),
                )
                await conn.commit()

    async def list_jobs(self) -> List[Job]:
        """Return all stored jobs."""
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute("SELECT payload FROM jobs ORDER BY updated_at DESC")
            rows = await cursor.fetchall()
            await cursor.close()

        jobs: List[Job] = []
        for (payload,) in rows:
            try:
                jobs.append(Job(**json.loads(payload)))
            except Exception as exc:
                logger.warning(f"Skipping invalid stored job payload: {exc}")
        return jobs

    async def list_clips(self, job_id: Optional[str] = None) -> List[Clip]:
        """Return clips, optionally filtered by job id."""
        await self.initialize()
        query = "SELECT payload FROM clips"
        params: tuple = ()

        if job_id:
            query += " WHERE job_id = ?"
            params = (job_id,)

        query += " ORDER BY updated_at DESC"

        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            await cursor.close()

        clips: List[Clip] = []
        for (payload,) in rows:
            try:
                clips.append(Clip(**json.loads(payload)))
            except Exception as exc:
                logger.warning(f"Skipping invalid stored clip payload: {exc}")
        return clips

    async def delete_job(self, job_id: str):
        """Delete job and all related clips."""
        await self.initialize()
        async with self._write_lock:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                await conn.execute("DELETE FROM clips WHERE job_id = ?", (job_id,))
                await conn.commit()

    async def delete_clip(self, clip_id: str):
        """Delete a clip by id."""
        await self.initialize()
        async with self._write_lock:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
                await conn.commit()

    async def get_job_clip_map(self) -> Dict[str, List[Clip]]:
        """Get all clips grouped by job id."""
        clips = await self.list_clips()
        mapping: Dict[str, List[Clip]] = {}
        for clip in clips:
            mapping.setdefault(clip.job_id, []).append(clip)
        return mapping


_job_store: Optional[JobStore] = None


def get_job_store() -> JobStore:
    """Return singleton job store."""
    global _job_store
    if _job_store is None:
        settings = get_settings()
        db_path = Path(settings.data_dir) / "viralclip.db"
        _job_store = JobStore(str(db_path))
    return _job_store
