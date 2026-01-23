# periodic_sync.py
"""
Periodic sync scheduler for keeping books up-to-date throughout the day.
Runs every 6 hours to check for new chapters in all unfinished books.
"""
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("periodic-sync")


class PeriodicSyncScheduler:
    """
    Scheduler that syncs unfinished books every N hours.

    Features:
    - Runs at configurable intervals (default: 6 hours)
    - Syncs all unfinished books to check for new chapters
    - Lower priority than manual syncs but runs more frequently than midnight sync
    - Can be triggered manually via API
    """

    def __init__(
        self,
        db_session_factory,
        job_manager,
        interval_hours: int = 6,
        sync_priority: int = 3,  # Lower than manual (10+), higher than midnight (1)
    ):
        self.db_session_factory = db_session_factory
        self.job_manager = job_manager
        self.interval_hours = interval_hours
        self.sync_priority = sync_priority
        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        self.last_sync_time: Optional[datetime] = None
        self.next_sync_time: Optional[datetime] = None

        logger.info(
            f"[PeriodicSync] Initialized - interval: {interval_hours}h, priority={sync_priority}"
        )

    def start(self):
        """Start the scheduler thread."""
        if self.running:
            logger.warning("[PeriodicSync] Already running")
            return

        self.running = True
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="periodic-sync-scheduler",
            daemon=True,
        )
        self.scheduler_thread.start()
        logger.info("[PeriodicSync] Scheduler started")

    def stop(self):
        """Stop the scheduler thread."""
        logger.info("[PeriodicSync] Stopping scheduler...")
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5.0)
        logger.info("[PeriodicSync] Scheduler stopped")

    def _scheduler_loop(self):
        """Main scheduler loop that runs sync every N hours."""
        logger.info("[PeriodicSync] Scheduler loop started")

        # Calculate first sync time (run immediately on startup, then every N hours)
        self.next_sync_time = datetime.now() + timedelta(seconds=60)  # First sync after 1 minute
        logger.info(f"[PeriodicSync] First sync scheduled for {self.next_sync_time}")

        while self.running:
            try:
                now = datetime.now()

                # Check if it's time to sync
                if self.next_sync_time and now >= self.next_sync_time:
                    logger.info(f"[PeriodicSync] Starting periodic sync at {now}")
                    self._run_periodic_sync()
                    self.last_sync_time = now
                    self.next_sync_time = now + timedelta(hours=self.interval_hours)
                    logger.info(f"[PeriodicSync] Next sync scheduled for {self.next_sync_time}")

                # Sleep for 1 minute before checking again
                time.sleep(60)

            except Exception as e:
                logger.error(f"[PeriodicSync] Scheduler loop error: {e}")
                time.sleep(60)

        logger.info("[PeriodicSync] Scheduler loop stopped")

    def trigger_sync(self):
        """Trigger an immediate sync (can be called manually via API)."""
        logger.info("[PeriodicSync] Manual trigger requested")
        try:
            self._run_periodic_sync()
            self.last_sync_time = datetime.now()
            # Reset next sync time to N hours from now
            self.next_sync_time = self.last_sync_time + timedelta(hours=self.interval_hours)
            logger.info(f"[PeriodicSync] Manual sync completed. Next sync at {self.next_sync_time}")
        except Exception as e:
            logger.error(f"[PeriodicSync] Manual sync failed: {e}")
            raise

    def _run_periodic_sync(self):
        """
        Run the periodic sync process.
        Enqueues all unfinished books for background sync.
        """
        from db_models import Book

        session = self.db_session_factory()
        try:
            # Get all unfinished books
            logger.info("[PeriodicSync] Fetching all unfinished books")

            unfinished_books = (
                session.query(Book)
                .filter(Book.status != "已完成")
                .all()
            )

            if not unfinished_books:
                logger.info("[PeriodicSync] No unfinished books to sync")
                return

            logger.info(f"[PeriodicSync] Found {len(unfinished_books)} unfinished books")

            # Enqueue all unfinished books with the job manager
            queued_count = 0
            skipped_count = 0

            for book in unfinished_books:
                if not self.running:
                    logger.info("[PeriodicSync] Stopping sync early (scheduler stopped)")
                    break

                try:
                    if self.job_manager:
                        success = self.job_manager.enqueue_sync(
                            book.id,
                            priority=self.sync_priority
                        )

                        if success:
                            queued_count += 1
                            logger.debug(f"[PeriodicSync] Queued book {book.id} ({book.name})")
                        else:
                            skipped_count += 1
                            logger.debug(f"[PeriodicSync] Skipped book {book.id} (already in queue)")

                except Exception as e:
                    logger.error(f"[PeriodicSync] Failed to queue book {book.id}: {e}")
                    skipped_count += 1

            logger.info(
                f"[PeriodicSync] Periodic sync completed - "
                f"queued: {queued_count}, skipped: {skipped_count}, "
                f"total: {len(unfinished_books)}"
            )

        except Exception as e:
            logger.error(f"[PeriodicSync] Error during periodic sync: {e}")
            import traceback
            traceback.print_exc()
        finally:
            session.close()

    def get_stats(self):
        """Get current sync statistics."""
        return {
            "running": self.running,
            "interval_hours": self.interval_hours,
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "next_sync_time": self.next_sync_time.isoformat() if self.next_sync_time else None,
            "priority": self.sync_priority,
        }


# Global instance
periodic_scheduler: Optional[PeriodicSyncScheduler] = None


def init_periodic_scheduler(
    db_session_factory,
    job_manager,
    interval_hours: int = 6,
    sync_priority: int = 3,
) -> PeriodicSyncScheduler:
    """Initialize the periodic sync scheduler."""
    global periodic_scheduler
    periodic_scheduler = PeriodicSyncScheduler(
        db_session_factory=db_session_factory,
        job_manager=job_manager,
        interval_hours=interval_hours,
        sync_priority=sync_priority,
    )
    return periodic_scheduler
