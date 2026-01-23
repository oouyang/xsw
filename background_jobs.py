# background_jobs.py
"""
Background job system for syncing book chapters and metadata.
Uses threading to avoid blocking the main request handlers.
"""
import threading
import time
import logging
from typing import Dict, Set, Optional, List
from queue import Queue, Empty
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger("background-jobs")


@dataclass
class SyncJob:
    """Represents a sync job for a book."""
    book_id: str
    priority: int = 0  # Higher priority = processed first
    added_at: float = 0.0

    def __post_init__(self):
        if self.added_at == 0.0:
            self.added_at = time.time()


class BackgroundJobManager:
    """
    Manages background jobs for syncing book chapters.

    Features:
    - Thread-safe job queue
    - Deduplication (same book not queued multiple times)
    - Priority-based processing
    - Configurable worker threads
    - Rate limiting to avoid overloading the scraping target
    """

    def __init__(
        self,
        num_workers: int = 2,
        rate_limit_seconds: float = 1.0,
        job_timeout_seconds: int = 300,
    ):
        self.job_queue: Queue[SyncJob] = Queue()
        self.active_jobs: Set[str] = set()
        self.completed_jobs: Dict[str, datetime] = {}
        self.failed_jobs: Dict[str, tuple[datetime, str]] = {}
        self.lock = threading.Lock()
        self.num_workers = num_workers
        self.rate_limit_seconds = rate_limit_seconds
        self.job_timeout_seconds = job_timeout_seconds
        self.workers: List[threading.Thread] = []
        self.running = False
        self._last_job_time = 0.0

        # Callbacks to be set by the app
        self.fetch_book_info_callback = None
        self.fetch_chapters_callback = None

        logger.info(f"[BackgroundJobManager] Initialized with {num_workers} workers, rate_limit={rate_limit_seconds}s")

    def start(self):
        """Start worker threads."""
        if self.running:
            logger.warning("[BackgroundJobManager] Already running")
            return

        self.running = True
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker,
                name=f"sync-worker-{i}",
                daemon=True,
            )
            worker.start()
            self.workers.append(worker)

        logger.info(f"[BackgroundJobManager] Started {self.num_workers} workers")

    def stop(self):
        """Stop all workers gracefully."""
        logger.info("[BackgroundJobManager] Stopping workers...")
        self.running = False
        # Wait for workers to finish (with timeout)
        for worker in self.workers:
            worker.join(timeout=5.0)
        self.workers.clear()
        logger.info("[BackgroundJobManager] All workers stopped")

    def enqueue_sync(self, book_id: str, priority: int = 0) -> bool:
        """
        Add a book sync job to the queue.

        Returns:
            True if job was added, False if already queued/active
        """
        with self.lock:
            # Check if already active or recently completed
            if book_id in self.active_jobs:
                logger.debug(f"[BackgroundJobManager] Book {book_id} already being synced")
                return False

            # Check if completed recently (within last 5 minutes)
            if book_id in self.completed_jobs:
                completed_at = self.completed_jobs[book_id]
                if datetime.now() - completed_at < timedelta(minutes=5):
                    logger.debug(f"[BackgroundJobManager] Book {book_id} synced recently, skipping")
                    return False

            # Add to queue
            job = SyncJob(book_id=book_id, priority=priority)
            self.job_queue.put(job)
            logger.info(f"[BackgroundJobManager] Queued sync job for book {book_id} (priority={priority})")
            return True

    def enqueue_batch(self, book_ids: List[str], priority: int = 0) -> int:
        """
        Enqueue multiple books for syncing.

        Returns:
            Number of jobs successfully queued
        """
        queued = 0
        for book_id in book_ids:
            if self.enqueue_sync(book_id, priority):
                queued += 1
        return queued

    def force_resync(self, book_id: str, priority: int = 10) -> bool:
        """
        Force a resync of a book, bypassing recent completion checks.
        Useful for resyncing books that may have missing chapters due to parsing issues.

        Args:
            book_id: The book ID to resync
            priority: Job priority (higher = first)

        Returns:
            True if job was queued, False if already active
        """
        with self.lock:
            # Check if already active
            if book_id in self.active_jobs:
                logger.debug(f"[BackgroundJobManager] Book {book_id} already being synced, cannot force resync")
                return False

            # Remove from completed jobs to bypass recent completion check
            if book_id in self.completed_jobs:
                del self.completed_jobs[book_id]
                logger.info(f"[BackgroundJobManager] Removed book {book_id} from completed cache for forced resync")

            # Add to queue
            job = SyncJob(book_id=book_id, priority=priority)
            self.job_queue.put(job)
            logger.info(f"[BackgroundJobManager] Force queued resync for book {book_id} (priority={priority})")
            return True

    def _worker(self):
        """Worker thread that processes sync jobs."""
        logger.info(f"[{threading.current_thread().name}] Worker started")

        while self.running:
            try:
                # Get next job (with timeout to check if we should stop)
                try:
                    job = self.job_queue.get(timeout=1.0)
                except Empty:
                    continue

                # Rate limiting
                now = time.time()
                elapsed = now - self._last_job_time
                if elapsed < self.rate_limit_seconds:
                    sleep_time = self.rate_limit_seconds - elapsed
                    time.sleep(sleep_time)

                self._last_job_time = time.time()

                # Mark as active
                with self.lock:
                    self.active_jobs.add(job.book_id)

                # Process the job
                try:
                    self._process_sync_job(job)

                    # Mark as completed
                    with self.lock:
                        self.completed_jobs[job.book_id] = datetime.now()
                        if job.book_id in self.failed_jobs:
                            del self.failed_jobs[job.book_id]

                    logger.info(f"[{threading.current_thread().name}] Successfully synced book {job.book_id}")

                except Exception as e:
                    logger.error(f"[{threading.current_thread().name}] Failed to sync book {job.book_id}: {e}")

                    # Mark as failed
                    with self.lock:
                        self.failed_jobs[job.book_id] = (datetime.now(), str(e))

                finally:
                    # Remove from active
                    with self.lock:
                        self.active_jobs.discard(job.book_id)

                    # Mark job as done
                    self.job_queue.task_done()

            except Exception as e:
                logger.error(f"[{threading.current_thread().name}] Worker error: {e}")

        logger.info(f"[{threading.current_thread().name}] Worker stopped")

    def _process_sync_job(self, job: SyncJob):
        """Process a single sync job."""
        book_id = job.book_id

        logger.info(f"[Sync] Starting sync for book {book_id}")

        # Step 1: Fetch book info (if callbacks are set)
        if self.fetch_book_info_callback:
            try:
                self.fetch_book_info_callback(book_id)
                logger.debug(f"[Sync] Fetched book info for {book_id}")
            except Exception as e:
                logger.warning(f"[Sync] Failed to fetch book info for {book_id}: {e}")

        # Step 2: Fetch all chapters
        if self.fetch_chapters_callback:
            try:
                self.fetch_chapters_callback(book_id)
                logger.debug(f"[Sync] Fetched chapters for {book_id}")
            except Exception as e:
                logger.warning(f"[Sync] Failed to fetch chapters for {book_id}: {e}")
                raise  # Re-raise to mark job as failed

        logger.info(f"[Sync] Completed sync for book {book_id}")

    def get_stats(self) -> Dict:
        """Get statistics about the job queue."""
        with self.lock:
            return {
                "queue_size": self.job_queue.qsize(),
                "active_jobs": len(self.active_jobs),
                "active_job_ids": list(self.active_jobs),
                "completed_count": len(self.completed_jobs),
                "failed_count": len(self.failed_jobs),
                "failed_jobs": {
                    book_id: {"failed_at": failed_at.isoformat(), "error": error}
                    for book_id, (failed_at, error) in self.failed_jobs.items()
                },
                "workers": self.num_workers,
                "running": self.running,
            }

    def clear_history(self):
        """Clear completed and failed job history."""
        with self.lock:
            self.completed_jobs.clear()
            self.failed_jobs.clear()
        logger.info("[BackgroundJobManager] Cleared job history")

    def clear_all(self):
        """Clear all job state including queue, completed, and failed jobs."""
        with self.lock:
            # Clear the job queue
            while not self.job_queue.empty():
                try:
                    self.job_queue.get_nowait()
                except Empty:
                    break

            # Clear history
            self.completed_jobs.clear()
            self.failed_jobs.clear()

            # Note: active_jobs is not cleared as jobs may still be processing
        logger.info("[BackgroundJobManager] Cleared all job state (queue, completed, failed)")


# Global job manager instance
job_manager: Optional[BackgroundJobManager] = None


def init_job_manager(
    num_workers: int = 2,
    rate_limit_seconds: float = 1.0,
    job_timeout_seconds: int = 300,
) -> BackgroundJobManager:
    """Initialize the background job manager."""
    global job_manager
    job_manager = BackgroundJobManager(
        num_workers=num_workers,
        rate_limit_seconds=rate_limit_seconds,
        job_timeout_seconds=job_timeout_seconds,
    )
    return job_manager
