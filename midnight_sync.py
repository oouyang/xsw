# midnight_sync.py
"""
Midnight sync scheduler for deferred book syncing.
Tracks book accesses and syncs them at midnight with slow rate limiting.
"""
import threading
import time
import logging
from datetime import datetime, time as dt_time
from typing import Optional

logger = logging.getLogger("midnight-sync")


class MidnightSyncScheduler:
    """
    Scheduler that runs sync jobs at midnight with slow rate limiting.

    Features:
    - Track book accesses and add to pending queue
    - Run sync at midnight (configurable time)
    - Slow rate limiting to avoid blocking by m.xsw.tw
    - Persistent queue using database
    """

    def __init__(
        self,
        db_session_factory,
        job_manager,
        sync_hour: int = 0,  # Midnight by default
        sync_minute: int = 0,
        slow_rate_limit: float = 5.0,  # 5 seconds between books
    ):
        self.db_session_factory = db_session_factory
        self.job_manager = job_manager
        self.sync_hour = sync_hour
        self.sync_minute = sync_minute
        self.slow_rate_limit = slow_rate_limit
        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        self.last_sync_date: Optional[datetime] = None

        logger.info(
            f"[MidnightSync] Initialized - sync time: {sync_hour:02d}:{sync_minute:02d}, "
            f"rate_limit={slow_rate_limit}s between books"
        )

    def start(self):
        """Start the scheduler thread."""
        if self.running:
            logger.warning("[MidnightSync] Already running")
            return

        self.running = True
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="midnight-sync-scheduler",
            daemon=True,
        )
        self.scheduler_thread.start()
        logger.info("[MidnightSync] Scheduler started")

    def stop(self):
        """Stop the scheduler thread."""
        logger.info("[MidnightSync] Stopping scheduler...")
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5.0)
        logger.info("[MidnightSync] Scheduler stopped")

    def track_book_access(self, book_id: str):
        """
        Track a book access and add to pending sync queue.
        Updates access count if already in queue.
        """
        from db_models import PendingSyncQueue

        session = self.db_session_factory()
        try:
            # Check if book is already in queue
            pending = session.query(PendingSyncQueue).filter_by(book_id=book_id).first()

            if pending:
                # Update existing entry
                pending.accessed_at = datetime.utcnow()
                pending.access_count += 1
                # Reset status if it was completed/failed
                if pending.sync_status in ["completed", "failed"]:
                    pending.sync_status = "pending"
                    pending.last_sync_attempt = None
                logger.debug(f"[MidnightSync] Updated access for book {book_id} (count={pending.access_count})")
            else:
                # Add new entry
                pending = PendingSyncQueue(
                    book_id=book_id,
                    added_at=datetime.utcnow(),
                    accessed_at=datetime.utcnow(),
                    access_count=1,
                    sync_status="pending",
                )
                session.add(pending)
                logger.info(f"[MidnightSync] Added book {book_id} to pending sync queue")

            session.commit()

        except Exception as e:
            logger.error(f"[MidnightSync] Failed to track access for {book_id}: {e}")
            try:
                session.rollback()
            except Exception as rollback_error:
                logger.debug(f"[MidnightSync] Rollback failed (no active transaction): {rollback_error}")
        finally:
            session.close()

    def _scheduler_loop(self):
        """Main scheduler loop that checks if it's time to sync."""
        logger.info("[MidnightSync] Scheduler loop started")

        while self.running:
            try:
                now = datetime.now()
                current_time = now.time()
                target_time = dt_time(self.sync_hour, self.sync_minute)

                # Check if we've passed the sync time and haven't synced today yet
                should_sync = False
                if self.last_sync_date is None or self.last_sync_date.date() < now.date():
                    # Check if current time is past target time
                    if current_time >= target_time:
                        should_sync = True

                if should_sync:
                    logger.info(f"[MidnightSync] Starting midnight sync at {now}")
                    self._run_midnight_sync()
                    self.last_sync_date = now
                    logger.info("[MidnightSync] Midnight sync completed")

                # Sleep for 1 minute before checking again
                time.sleep(60)

            except Exception as e:
                logger.error(f"[MidnightSync] Scheduler loop error: {e}")
                time.sleep(60)

        logger.info("[MidnightSync] Scheduler loop stopped")

    def _run_midnight_sync(self):
        """
        Run the midnight sync process.
        First adds all unfinished books to the queue, then processes all pending books with slow rate limiting.
        """
        from db_models import PendingSyncQueue, Book

        session = self.db_session_factory()
        try:
            # STEP 1: Add all unfinished books to the pending queue
            logger.info("[MidnightSync] Step 1: Adding all unfinished books to sync queue")

            unfinished_books = (
                session.query(Book)
                .filter(Book.status != "已完成")
                .all()
            )

            logger.info(f"[MidnightSync] Found {len(unfinished_books)} unfinished books")

            added_count = 0
            for book in unfinished_books:
                # Check if already in queue
                existing = session.query(PendingSyncQueue).filter_by(book_id=book.id).first()

                if existing:
                    # Update existing entry - reset to pending if was completed/failed
                    if existing.sync_status in ["completed", "failed"]:
                        existing.sync_status = "pending"
                        existing.accessed_at = datetime.utcnow()
                        existing.access_count += 1
                        existing.priority = 1  # Give unfinished books priority 1
                        logger.debug(f"[MidnightSync] Reset status for unfinished book: {book.id}")
                else:
                    # Add new entry for unfinished book
                    pending = PendingSyncQueue(
                        book_id=book.id,
                        added_at=datetime.utcnow(),
                        accessed_at=datetime.utcnow(),
                        access_count=1,
                        sync_status="pending",
                        priority=1  # Unfinished books get priority 1
                    )
                    session.add(pending)
                    added_count += 1
                    logger.debug(f"[MidnightSync] Added unfinished book to queue: {book.id}")

            session.commit()
            logger.info(f"[MidnightSync] Added {added_count} new unfinished books to sync queue")

            # STEP 2: Get all pending books, ordered by priority (high to low) and access count (high to low)
            logger.info("[MidnightSync] Step 2: Processing pending sync queue")

            pending_books = (
                session.query(PendingSyncQueue)
                .filter_by(sync_status="pending")
                .order_by(PendingSyncQueue.priority.desc(), PendingSyncQueue.access_count.desc())
                .all()
            )

            if not pending_books:
                logger.info("[MidnightSync] No pending books to sync")
                return

            logger.info(f"[MidnightSync] Found {len(pending_books)} books to sync")

            # Process each book with slow rate limiting
            for i, pending in enumerate(pending_books):
                if not self.running:
                    logger.info("[MidnightSync] Stopping sync early (scheduler stopped)")
                    break

                try:
                    logger.info(
                        f"[MidnightSync] Syncing book {i+1}/{len(pending_books)}: "
                        f"{pending.book_id} (accessed {pending.access_count} times)"
                    )

                    # Update status to syncing
                    pending.sync_status = "syncing"
                    pending.last_sync_attempt = datetime.utcnow()
                    session.commit()

                    # Enqueue the sync job (this will use the normal background job system)
                    if self.job_manager:
                        success = self.job_manager.enqueue_sync(
                            pending.book_id,
                            priority=pending.priority
                        )

                        if success:
                            # Mark as completed (the background job will handle actual syncing)
                            pending.sync_status = "completed"
                            logger.info(f"[MidnightSync] Queued sync for {pending.book_id}")
                        else:
                            # Already being synced or recently synced
                            pending.sync_status = "completed"
                            logger.debug(f"[MidnightSync] Book {pending.book_id} already synced/syncing")

                    session.commit()

                    # Slow rate limiting - wait between books to avoid blocking
                    if i < len(pending_books) - 1:  # Don't sleep after last book
                        logger.debug(f"[MidnightSync] Waiting {self.slow_rate_limit}s before next book...")
                        time.sleep(self.slow_rate_limit)

                except Exception as e:
                    logger.error(f"[MidnightSync] Failed to sync book {pending.book_id}: {e}")
                    pending.sync_status = "failed"
                    session.commit()

            logger.info(f"[MidnightSync] Completed processing {len(pending_books)} books")

        except Exception as e:
            logger.error(f"[MidnightSync] Error during midnight sync: {e}")
        finally:
            session.close()

    def get_queue_stats(self) -> dict:
        """Get statistics about the pending sync queue."""
        from db_models import PendingSyncQueue

        session = self.db_session_factory()
        try:
            pending_count = session.query(PendingSyncQueue).filter_by(sync_status="pending").count()
            syncing_count = session.query(PendingSyncQueue).filter_by(sync_status="syncing").count()
            completed_count = session.query(PendingSyncQueue).filter_by(sync_status="completed").count()
            failed_count = session.query(PendingSyncQueue).filter_by(sync_status="failed").count()
            total_count = session.query(PendingSyncQueue).count()

            return {
                "total": total_count,
                "pending": pending_count,
                "syncing": syncing_count,
                "completed": completed_count,
                "failed": failed_count,
                "last_sync_date": self.last_sync_date.isoformat() if self.last_sync_date else None,
                "next_sync_time": f"{self.sync_hour:02d}:{self.sync_minute:02d}",
                "slow_rate_limit": self.slow_rate_limit,
            }

        finally:
            session.close()

    def enqueue_unfinished_books(self) -> int:
        """
        Manually enqueue all unfinished books to the pending sync queue.
        Returns the number of books added.
        """
        from db_models import PendingSyncQueue, Book

        session = self.db_session_factory()
        try:
            # Get all unfinished books
            unfinished_books = (
                session.query(Book)
                .filter(Book.status != "已完成")
                .all()
            )

            logger.info(f"[MidnightSync] Found {len(unfinished_books)} unfinished books")

            added_count = 0
            for book in unfinished_books:
                # Check if already in queue
                existing = session.query(PendingSyncQueue).filter_by(book_id=book.id).first()

                if existing:
                    # Update existing entry - reset to pending if was completed/failed
                    if existing.sync_status in ["completed", "failed"]:
                        existing.sync_status = "pending"
                        existing.accessed_at = datetime.utcnow()
                        existing.access_count += 1
                        existing.priority = 1
                        logger.debug(f"[MidnightSync] Reset status for unfinished book: {book.id}")
                else:
                    # Add new entry for unfinished book
                    pending = PendingSyncQueue(
                        book_id=book.id,
                        added_at=datetime.utcnow(),
                        accessed_at=datetime.utcnow(),
                        access_count=1,
                        sync_status="pending",
                        priority=1
                    )
                    session.add(pending)
                    added_count += 1
                    logger.debug(f"[MidnightSync] Added unfinished book to queue: {book.id}")

            session.commit()
            logger.info(f"[MidnightSync] Enqueued {added_count} new unfinished books for sync")
            return added_count

        except Exception as e:
            logger.error(f"[MidnightSync] Failed to enqueue unfinished books: {e}")
            try:
                session.rollback()
            except Exception as rollback_error:
                logger.debug(f"[MidnightSync] Rollback failed (no active transaction): {rollback_error}")
            return 0
        finally:
            session.close()

    def clear_completed(self):
        """Clear completed and failed entries from the queue."""
        from db_models import PendingSyncQueue

        session = self.db_session_factory()
        try:
            deleted = (
                session.query(PendingSyncQueue)
                .filter(PendingSyncQueue.sync_status.in_(["completed", "failed"]))
                .delete(synchronize_session=False)
            )
            session.commit()
            logger.info(f"[MidnightSync] Cleared {deleted} completed/failed entries")
            return deleted

        except Exception as e:
            logger.error(f"[MidnightSync] Failed to clear completed entries: {e}")
            try:
                session.rollback()
            except Exception as rollback_error:
                logger.debug(f"[MidnightSync] Rollback failed (no active transaction): {rollback_error}")
            return 0
        finally:
            session.close()


# Global scheduler instance
midnight_scheduler: Optional[MidnightSyncScheduler] = None


def init_midnight_scheduler(
    db_session_factory,
    job_manager,
    sync_hour: int = 0,
    sync_minute: int = 0,
    slow_rate_limit: float = 5.0,
) -> MidnightSyncScheduler:
    """Initialize the midnight sync scheduler."""
    global midnight_scheduler
    midnight_scheduler = MidnightSyncScheduler(
        db_session_factory=db_session_factory,
        job_manager=job_manager,
        sync_hour=sync_hour,
        sync_minute=sync_minute,
        slow_rate_limit=slow_rate_limit,
    )
    return midnight_scheduler
