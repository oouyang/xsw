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
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.pool import StaticPool
import os

Base = declarative_base()


class Book(Base):
    """Book metadata from book home pages."""

    __tablename__ = "books"

    id = Column(String, primary_key=True)  # book_id
    name = Column(String, nullable=False)
    author = Column(String)
    type = Column(String)  # category
    status = Column(String)  # 進行中/已完成
    update = Column(String)  # last update date from site

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
        print(f"[DB] Tables created successfully")

    def get_session(self):
        """Get a new database session."""
        return self.SessionLocal()

    def enable_wal_mode(self):
        """Enable WAL (Write-Ahead Logging) mode for better concurrency."""
        with self.engine.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
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
