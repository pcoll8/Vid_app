"""
Job Queue Service
Bounded async queue with worker concurrency and backpressure.
"""

import asyncio
from typing import Awaitable, Callable, Optional, Set

from ..utils.logger import get_logger

logger = get_logger()

JobProcessor = Callable[[str], Awaitable[None]]


class JobQueue:
    """Worker queue for processing jobs with controlled concurrency."""

    def __init__(self):
        self._queue: asyncio.Queue[Optional[str]] = asyncio.Queue(maxsize=10)
        self._workers: list[asyncio.Task] = []
        self._processor: Optional[JobProcessor] = None
        self._running = False
        self._worker_count = 1
        self._max_pending = 10
        self._queued_ids: Set[str] = set()
        self._active_ids: Set[str] = set()

    def configure(
        self,
        processor: JobProcessor,
        worker_count: int,
        max_pending: int
    ):
        """Configure queue processor and capacity before start."""
        if self._running:
            return

        self._processor = processor
        self._worker_count = max(1, worker_count)
        self._max_pending = max(1, max_pending)
        self._queue = asyncio.Queue(maxsize=self._max_pending)

    async def start(self):
        """Start worker tasks."""
        if self._running:
            return
        if self._processor is None:
            raise RuntimeError("JobQueue processor is not configured")

        self._running = True
        self._workers = [
            asyncio.create_task(self._worker_loop(index + 1))
            for index in range(self._worker_count)
        ]
        logger.info(
            f"Job queue started (workers={self._worker_count}, max_pending={self._max_pending})"
        )

    async def stop(self):
        """Stop worker tasks."""
        if not self._running:
            return

        self._running = False
        for _ in self._workers:
            await self._queue.put(None)

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._queued_ids.clear()
        self._active_ids.clear()
        logger.info("Job queue stopped")

    async def enqueue(self, job_id: str) -> bool:
        """Enqueue a job if capacity allows."""
        if not self._running:
            raise RuntimeError("Job queue is not running")

        if job_id in self._queued_ids or job_id in self._active_ids:
            return True

        if self._queue.full():
            return False

        self._queued_ids.add(job_id)
        await self._queue.put(job_id)
        return True

    def can_accept(self) -> bool:
        """Check if queue has free pending capacity."""
        return not self._queue.full()

    def stats(self) -> dict:
        """Current queue statistics."""
        return {
            "pending": self._queue.qsize(),
            "active": len(self._active_ids),
            "max_pending": self._max_pending,
            "workers": self._worker_count,
            "running": self._running,
        }

    async def _worker_loop(self, worker_id: int):
        while True:
            job_id = await self._queue.get()
            if job_id is None:
                self._queue.task_done()
                return

            self._queued_ids.discard(job_id)
            self._active_ids.add(job_id)
            try:
                await self._processor(job_id)  # type: ignore[arg-type]
            except Exception as exc:
                logger.exception(f"Worker {worker_id} failed job {job_id}: {exc}")
            finally:
                self._active_ids.discard(job_id)
                self._queue.task_done()


_job_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    """Return singleton job queue."""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue()
    return _job_queue
