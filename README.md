# 看小說 (XSW) - Novel Reading Web Application

A full-stack Chinese novel reading platform with intelligent caching, background synchronization, comprehensive search, and administrative tools.

## 📖 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Features Documentation](#features-documentation)
- [API Documentation](#api-documentation)
- [Development](#development)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

**看小說 (XSW)** is a modern, feature-rich web application for reading Chinese novels. Built with FastAPI and Vue 3, it provides an exceptional reading experience through intelligent caching, background synchronization, and a polished user interface.

### Tech Stack

**Backend:**
- Python 3.11+ with FastAPI
- SQLAlchemy ORM with SQLite database
- BeautifulSoup4 for HTML parsing
- Background job system with threading
- SMTP email support with attachments

**Frontend:**
- Vue 3.5+ with TypeScript and Composition API
- Quasar Framework 2.16+ for UI components
- Pinia 3.0+ for state management
- Axios for API communication
- OpenCC-JS for Chinese text conversion

---

## ⭐ Key Features

### Core Reading Experience
- 📖 **Adaptive Two-Phase Loading** - Content appears in 1-2 seconds regardless of book size
- 🎨 **Modern UI with Dark Mode** - Polished interface with smooth animations
- ⌨️ **Keyboard Shortcuts** - Arrow keys for chapter navigation
- 🔍 **Comprehensive Search** - Search across book names, authors, chapters, and content
- 🌐 **Multi-Language Support** - Traditional Chinese, Simplified Chinese, English
- 📱 **Responsive Design** - Mobile-optimized reading experience

### Smart Caching System
- 💾 **3-Tier Hybrid Cache** - Memory (TTL) → Database (SQLite) → Web scraping
- 🔄 **Automatic Background Sync** - Books cached proactively when browsing categories
- 🌙 **Midnight Sync Queue** - Automatic overnight updates for accessed books
- 📊 **Unfinished Books Auto-Sync** - All ongoing books stay up-to-date automatically

### Administrative Tools
- 👑 **Admin Panel** - Comprehensive management interface
- 🔐 **Secure Authentication** - Google OAuth2 SSO with JWT tokens and email whitelist
- 📧 **SMTP Email System** - Send emails with file attachments
- 📁 **File Upload** - Upload files to static folder
- 📈 **Statistics Dashboard** - Cache, jobs, and sync metrics
- 🔧 **Cache Management** - Clear and invalidate caches
- 🕐 **Sync Control** - Manual trigger, queue management
- 🔒 **Password Management** - Change admin password

### Search & Discovery
- 🔎 **Multi-Field Search** - Books, authors, chapters, full-text content
- 📑 **Relevance Scoring** - Intelligent ranking of search results
- 📋 **Grouped Results** - Matches organized by book
- 💡 **Context Snippets** - Preview matched content

### Developer Experience
- 📝 **OpenAPI Documentation** - Auto-generated API docs
- 🛡️ **Type Safety** - TypeScript throughout frontend
- 🧪 **Error Handling** - Context-aware error messages with smart retry
- 📊 **Observable** - Comprehensive logging and metrics

---

## 🏗️ Architecture

### Backend Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI Backend                      │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐    ┌────────────────┐                │
│  │   REST API   │───▶│  Cache Manager │                │
│  └──────────────┘    └────────────────┘                │
│                              │                            │
│                              ├──▶ Memory Cache (TTL)     │
│                              ├──▶ SQLite Database        │
│                              └──▶ Web Scraper            │
│                                                           │
│  ┌──────────────────┐    ┌─────────────────────┐       │
│  │ Background Jobs  │    │  Midnight Sync      │       │
│  │  - 2 Workers     │    │  - Scheduled sync   │       │
│  │  - Rate limited  │    │  - Priority queue   │       │
│  └──────────────────┘    └─────────────────────┘       │
│                                                           │
│  ┌──────────────────┐    ┌─────────────────────┐       │
│  │ Search Engine    │    │  Email System       │       │
│  │  - Full-text     │    │  - SMTP support     │       │
│  │  - Multi-field   │    │  - Attachments      │       │
│  └──────────────────┘    └─────────────────────┘       │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### 3-Tier Caching Strategy

1. **Memory Layer (TTL Cache)**
   - ⚡ Fastest, volatile cache
   - Configurable TTL (default: 15 minutes)
   - Thread-safe with LRU eviction
   - Holds recently accessed content

2. **Database Layer (SQLite)**
   - 💾 Persistent storage
   - Survives container restarts
   - Stores book metadata and chapters
   - Indexed for fast queries

3. **Web Scraping Layer**
   - 🌐 Fallback when cache misses
   - Scrapes from m.xsw.tw
   - Rate-limited to avoid blocking
   - Stores results to database

---

## 🚀 Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for local development)
- Python 3.11+ (for local development)

### Quick Start with Docker

1. **Clone the repository**

2. **Create environment file (.env):**
```bash
# Backend Configuration
BASE_URL=https://m.xsw.tw
HTTP_TIMEOUT=10
CACHE_TTL_SECONDS=900
CACHE_MAX_ITEMS=500
CHAPTERS_PAGE_SIZE=20
LOG_LEVEL=INFO

# Database
DB_PATH=xsw_cache.db

# Background Jobs
BG_JOB_WORKERS=2
BG_JOB_RATE_LIMIT=2.0

# Midnight Sync
MIDNIGHT_SYNC_HOUR=0
MIDNIGHT_SYNC_MINUTE=0
MIDNIGHT_SYNC_RATE_LIMIT=5.0

# Periodic Sync (6 hours)
PERIODIC_SYNC_INTERVAL=6
PERIODIC_SYNC_PRIORITY=3

# Docker
img=xsw
tag=latest
```

3. **Build and run:**
```bash
# Build everything
docker compose -f compose.yml -f docker/build.yml up -d --build

# Or build separately
docker compose -f compose.yml -f docker/build.yml up -d xsw --build  # Backend
docker compose -f compose.yml -f docker/build.yml up -d web --build  # Frontend
```

4. **Access the application:**
- Frontend: http://localhost:2345
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/xsw/api/docs
- Health Check: http://localhost:8000/xsw/api/health

### Default Admin Credentials

- **Username:** `admin`
- **Password:** `admin`

⚠️ **Security Note:** Change the admin password in production using the admin panel.

---

## ⚙️ Configuration

### Backend Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_URL` | `https://m.xsw.tw` | Target scraping site |
| `HTTP_TIMEOUT` | `10` | Default HTTP timeout (seconds) |
| `CACHE_TTL_SECONDS` | `900` | Memory cache TTL (15 minutes) |
| `CACHE_MAX_ITEMS` | `500` | Max items in memory cache |
| `CHAPTERS_PAGE_SIZE` | `20` | Chapters per page |
| `DB_PATH` | `xsw_cache.db` | SQLite database path |
| `BG_JOB_WORKERS` | `2` | Background worker threads |
| `BG_JOB_RATE_LIMIT` | `2.0` | Seconds between background jobs |
| `MIDNIGHT_SYNC_HOUR` | `0` | Hour to run midnight sync (0-23) |
| `MIDNIGHT_SYNC_MINUTE` | `0` | Minute to run sync (0-59) |
| `MIDNIGHT_SYNC_RATE_LIMIT` | `5.0` | Seconds between syncing books |
| `PERIODIC_SYNC_INTERVAL` | `6` | Hours between periodic syncs |
| `PERIODIC_SYNC_PRIORITY` | `3` | Priority for periodic sync jobs |
| `RATE_LIMIT_ENABLED` | `true` | Enable/disable progressive rate limiting |
| `RATE_LIMIT_WHITELIST` | `127.0.0.1,::1` | Comma-separated IPs/CIDRs to whitelist |

### Rate Limiting

The API includes progressive rate limiting to prevent abuse. Requests are tracked per client IP in a 1-minute sliding window.

**Rate Limit Thresholds:**
- **0-50 requests/min:** No delay (normal speed)
- **51-100 requests/min:** 1 second delay per request
- **101-200 requests/min:** 10 seconds delay per request
- **201-500 requests/min:** 60 seconds (1 minute) delay per request
- **500+ requests/min:** 300 seconds (5 minutes) delay per request

**Whitelist Support:**
- Single IPs: `127.0.0.1`, `::1`
- CIDR ranges: `10.0.0.0/8`, `192.168.0.0/16`
- Multiple entries: Comma-separated in `RATE_LIMIT_WHITELIST`

**Admin Endpoint:**
- `GET /admin/rate-limit/stats` - View active clients and request counts

---

## 🔐 Admin Authentication

The admin panel is secured with JWT-based authentication supporting two methods:

### Authentication Methods

1. **Google OAuth2 SSO** (Primary, Recommended)
   - Secure authentication via Google accounts
   - No password management required
   - Email whitelist for access control
   - Profile picture integration

2. **Password Authentication** (Fallback, Emergency Access Only)
   - Email/password login
   - Default admin account: `admin@localhost` / `admin`
   - Available in collapsible section for emergency access

### Quick Setup

**Backend Environment Variables (.env):**
```bash
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
ADMIN_EMAIL_WHITELIST=admin@example.com,user2@example.com
JWT_SECRET=generate-with-openssl-rand-hex-32
JWT_EXPIRATION_HOURS=24
```

**Frontend Environment Variables (.env.local):**
```bash
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

### Default Credentials (Password Fallback)

- **Email:** `admin@localhost`
- **Password:** `admin`

⚠️ **Security Warning:** Change the default password immediately in production! It's for initial setup only.

### Setup Guide

For detailed Google Cloud Console setup and configuration:
- **[Complete Google SSO Setup Guide](docs/GOOGLE_SSO_SETUP.md)** - Step-by-step instructions

### Key Security Features

- **JWT Tokens:** 24-hour expiration (configurable)
- **Email Whitelist:** Only specified emails can authenticate via Google SSO
- **Protected Endpoints:** All `/admin/*` endpoints require valid JWT token
- **Automatic Token Refresh:** Token persists across page refreshes via localStorage
- **401 Handling:** Automatic logout on token expiration

### Emergency Access

If you lose access to Google SSO:
1. Use password authentication (expand "Password Login (Fallback)" section)
2. Log in with `admin@localhost` / `admin`
3. Or reset password via server console (see setup guide)

---

## 📚 Features Documentation

### Background Job System

Automatically pre-caches books when browsing categories.

**See:** [BACKGROUND_JOBS.md](BACKGROUND_JOBS.md)

### Midnight Sync Queue

Deferred synchronization system that updates accessed books overnight.

**See:** [MIDNIGHT_SYNC.md](MIDNIGHT_SYNC.md), [UNFINISHED_BOOKS_SYNC.md](UNFINISHED_BOOKS_SYNC.md)

### Two-Phase Loading

Dramatically improves perceived performance - content appears in 1-2 seconds.

**See:** [TWO_PHASE_LOADING.md](TWO_PHASE_LOADING.md)

### Comprehensive Search

Powerful full-text search across all content with relevance scoring.

**See:** [SEARCH_API.md](SEARCH_API.md)

### Admin Panel

Comprehensive administrative interface with statistics and management tools.

**See:** [ADMIN_PANEL.md](ADMIN_PANEL.md)

### Frontend Improvements

Modern, polished user experience with smooth loading and error handling.

**See:** [FRONTEND_IMPROVEMENTS.md](FRONTEND_IMPROVEMENTS.md)

---

## 📋 API Documentation

Full API documentation available at: http://localhost:8000/xsw/api/docs

### Quick Reference

**Book Management:**
- `GET /books/{book_id}` - Get book metadata
- `GET /books/{book_id}/chapters` - Get chapter list
- `GET /books/{book_id}/chapters/{chapter_num}` - Get chapter content

**Search:**
- `GET /search?q=keyword` - Search books and content

**Admin:**
- `GET /admin/midnight-sync/stats` - Sync queue statistics
- `POST /admin/midnight-sync/trigger` - Manually trigger sync
- `POST /admin/smtp/test` - Test SMTP connection
- `POST /admin/upload` - Upload file
- `POST /admin/email/send` - Send email with attachments

**Health:**
- `GET /health` - System health check

---

## 🛠️ Development

### Backend Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn main_optimized:app --reload --port 8000

# Access API docs
open http://localhost:8000/xsw/api/docs
```

### Frontend Development

```bash
# Install dependencies
npm install

# Run Quasar dev server
npm run dev

# Access application
open http://localhost:9000
```

---

## 🚢 Deployment

### Production Build

```bash
# Build all containers
docker compose -f compose.yml -f docker/build.yml build

# Run with production config
docker compose --env-file .env.production up -d
```

### Reverse Proxy (nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name xsw.example.com;

    # Frontend
    location / {
        proxy_pass http://localhost:2345;
    }

    # Backend API
    location /xsw/api {
        proxy_pass http://localhost:8000;
        proxy_read_timeout 300s;
    }
}
```

---

## 🐛 Troubleshooting

### Database Issues

```bash
# Clear database
docker compose down
docker volume rm xsw_xsw_data
docker compose up -d
```

### Background Jobs Not Processing

```bash
# Check worker status
curl http://localhost:8000/xsw/api/admin/jobs/stats

# Check logs
docker logs xsw --tail 100 -f
```

### SMTP Email Issues

```bash
# Test SMTP connection
curl -X POST http://localhost:8000/xsw/api/admin/smtp/test

# Check SMTP logs
docker logs xsw | grep "\[EmailSender\]"
```

---

## 📂 Project Structure

```
xsw/
├── backend/
│   ├── main_optimized.py          # FastAPI application
│   ├── cache_manager.py            # Cache system
│   ├── db_models.py                # Database models
│   ├── background_jobs.py          # Job queue
│   ├── midnight_sync.py            # Midnight scheduler
│   ├── periodic_sync.py            # Periodic scheduler
│   ├── email_sender.py             # SMTP email
│   └── parser.py                   # HTML parsing
│
├── frontend/src/
│   ├── pages/                     # Route pages
│   ├── components/                # Vue components
│   ├── stores/                    # Pinia stores
│   ├── services/                  # API clients
│   └── i18n/                      # Translations
│
├── docker/                        # Docker configs
├── compose.yml                    # Docker Compose
└── docs/                         # Documentation
```

---

## 📄 License

This project is for educational purposes only.

---

**Built with ❤️ using FastAPI, Vue 3, and Quasar**
