# db_models.py
"""
SQLAlchemy models for persistent storage of scraped novel data.
Database-first caching strategy: check DB before fetching from web.
"""
from datetime import datetime
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
)
from sqlalchemy.sql import text as sql_text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.pool import StaticPool
import os

Base = declarative_base()


class Book(Base):
    """Book metadata from book home pages."""

    __tablename__ = "books"

    id = Column(String, primary_key=True)  # book_id (czbooks ID)
    public_id = Column(String, unique=True, index=True)  # our random ID for URLs
    name = Column(String, nullable=False)
    author = Column(String)
    type = Column(String)  # category
    status = Column(String)  # 進行中/已完成
    update = Column(String)  # last update date from site
    description = Column(Text)  # book intro/synopsis
    bookmark_count = Column(Integer)  # 收藏數
    view_count = Column(Integer)  # 觀看數

    # Last chapter info
    last_chapter_num = Column(Integer)
    last_chapter_title = Column(String)
    last_chapter_url = Column(String)

    # Metadata
    source_url = Column(String, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_scraped_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    chapters = relationship("Chapter", back_populates="book", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Book(id='{self.id}', name='{self.name}', author='{self.author}')>"


class Chapter(Base):
    """Chapter content and metadata."""

    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    public_id = Column(String, unique=True, index=True)  # our random ID for URLs
    book_id = Column(String, ForeignKey("books.id"), nullable=False)
    chapter_num = Column(Integer, nullable=False)
    title = Column(String)
    url = Column(String, unique=True)
    text = Column(Text)  # Full chapter content

    # Metadata
    word_count = Column(Integer)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    book = relationship("Book", back_populates="chapters")

    # Indexes
    __table_args__ = (
        Index("idx_book_chapter", "book_id", "chapter_num", unique=True),
        Index("idx_chapter_url", "url"),
    )

    def __repr__(self):
        return f"<Chapter(book_id='{self.book_id}', num={self.chapter_num}, title='{self.title}')>"


class Category(Base):
    """Novel categories discovered from homepage."""

    __tablename__ = "categories"

    id = Column(String, primary_key=True)  # cat_id
    name = Column(String)
    url = Column(String, unique=True)
    discovered_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Category(id='{self.id}', name='{self.name}')>"


class ScrapeLog(Base):
    """Audit log for scraping operations (optional, for debugging)."""

    __tablename__ = "scrape_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint = Column(String)
    book_id = Column(String)
    chapter_num = Column(Integer)
    success = Column(Boolean)
    status_code = Column(Integer)
    error_message = Column(Text)
    response_time_ms = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_scrape_timestamp", "timestamp"),
        Index("idx_scrape_book", "book_id"),
    )


class PendingSyncQueue(Base):
    """Queue of books that need to be synced at midnight."""

    __tablename__ = "pending_sync_queue"

    book_id = Column(String, primary_key=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    accessed_at = Column(DateTime, default=datetime.utcnow)  # Last time book was accessed
    access_count = Column(Integer, default=1)  # Number of times accessed
    priority = Column(Integer, default=0)  # Higher = sync sooner
    last_sync_attempt = Column(DateTime, nullable=True)  # Last time sync was attempted
    sync_status = Column(String, default="pending")  # pending, syncing, completed, failed

    # Indexes
    __table_args__ = (
        Index("idx_sync_status", "sync_status"),
        Index("idx_accessed_at", "accessed_at"),
    )

    def __repr__(self):
        return f"<PendingSyncQueue(book_id='{self.book_id}', status='{self.sync_status}', access_count={self.access_count})>"


class SmtpSettings(Base):
    """SMTP configuration for sending emails."""

    __tablename__ = "smtp_settings"

    id = Column(Integer, primary_key=True, default=1)  # Singleton: only one row
    smtp_host = Column(String, nullable=False)
    smtp_port = Column(Integer, nullable=False, default=587)
    smtp_user = Column(String, nullable=False)
    smtp_password = Column(String, nullable=False)  # Should be encrypted in production
    use_tls = Column(Boolean, default=True)
    use_ssl = Column(Boolean, default=False)
    from_email = Column(String, nullable=True)
    from_name = Column(String, default="看小說 Admin")

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_test_at = Column(DateTime, nullable=True)
    last_test_status = Column(String, nullable=True)  # success, error

    def __repr__(self):
        return f"<SmtpSettings(host='{self.smtp_host}', port={self.smtp_port}, user='{self.smtp_user}')>"


class AdminUser(Base):
    """Admin user authentication records for Google OAuth and password authentication."""

    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False)
    auth_method = Column(String, nullable=False)  # 'google' or 'password'
    password_hash = Column(String, nullable=True)  # Only for password auth
    is_active = Column(Boolean, default=True)

    # Google OAuth specific
    google_id = Column(String, unique=True, nullable=True)
    picture_url = Column(String, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    # Indexes
    __table_args__ = (
        Index("idx_admin_email", "email"),
        Index("idx_admin_google_id", "google_id"),
    )

    def __repr__(self):
        return f"<AdminUser(email='{self.email}', auth_method='{self.auth_method}', is_active={self.is_active})>"


# Database connection and session management
class DatabaseManager:
    """Manages SQLite database connection and session lifecycle."""

    def __init__(self, db_url: str = None):
        if db_url is None:
            db_path = os.getenv("DB_PATH", "xsw_cache.db")
            db_url = f"sqlite:///{db_path}"

        # Use StaticPool for SQLite to handle threading properly
        self.engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=os.getenv("DB_ECHO", "false").lower() == "true"
        )

        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

    def create_tables(self):
        """Create all tables in the database."""
        Base.metadata.create_all(bind=self.engine)
        print("[DB] Tables created successfully")

    def get_session(self):
        """Get a new database session."""
        return self.SessionLocal()

    def enable_wal_mode(self):
        """Enable WAL (Write-Ahead Logging) mode for better concurrency."""
        with self.engine.connect() as conn:
            conn.execute(sql_text("PRAGMA journal_mode=WAL"))
            conn.execute(sql_text("PRAGMA synchronous=NORMAL"))
            conn.execute(sql_text("PRAGMA cache_size=-64000"))  # 64MB cache
            conn.commit()
            print("[DB] WAL mode enabled")


# Global database manager instance (initialized in main.py)
db_manager: DatabaseManager = None


def init_database(db_url: str = None) -> DatabaseManager:
    """Initialize the database and return the manager instance."""
    global db_manager
    db_manager = DatabaseManager(db_url)
    db_manager.create_tables()
    db_manager.enable_wal_mode()
    return db_manager


def get_db_session():
    """Dependency for FastAPI routes to get database session."""
    if db_manager is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()
