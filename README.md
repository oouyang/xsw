# XSW - Novel Reading Web Application

A full-stack web application for reading Chinese novels with web scraping, hybrid caching, and modern UI.

## 📖 Overview

This project consists of:
- **Backend (xsw)**: FastAPI-based web scraper with hybrid caching (SQLite + in-memory)
- **Frontend (web)**: Vue 3 + Quasar framework SPA with Pinia state management
- **Deployment**: Docker Compose with separate containers for backend and frontend

## 🏗️ Architecture

### Backend Architecture

The backend uses a **3-tier hybrid caching strategy** for optimal performance:

1. **Memory Layer (TTL Cache)**:
   - Fastest, volatile cache with configurable TTL (default 15 minutes)
   - Thread-safe with LRU eviction when full
   - Holds recently accessed book info and chapter content

2. **Database Layer (SQLite)**:
   - Persistent cache stored in `/app/data/` volume
   - Stores book metadata and chapter content
   - Survives container restarts

3. **Web Scraping Layer**:
   - Fallback when cache misses occur
   - Scrapes from m.xsw.tw (mobile site)
   - Respects timeouts: 10s default, extended for batch operations

**Key Backend Features:**
- FastAPI REST API with OpenAPI documentation
- Server-side pagination (20 chapters per page)
- Extended timeouts for long-running operations (5 minutes for all chapters, 2 minutes for chapter content)
- Traditional Chinese text conversion support
- CORS enabled for cross-origin requests
- Robust error handling with fallback strategies

**Technology Stack:**
- Python 3.11+
- FastAPI for REST API
- SQLAlchemy ORM for database operations
- BeautifulSoup4 for HTML parsing
- Pydantic for data validation
- SQLite for persistent storage

### Frontend Architecture

Modern Vue 3 application with enterprise-grade state management:

**Key Frontend Features:**
- Vue 3 Composition API with `<script setup>` syntax
- Pinia store for centralized state management
- LocalStorage persistence for offline reading list
- Quasar UI components for mobile-responsive design
- Axios for API communication with dynamic timeouts
- Chinese text conversion (Simplified ⟷ Traditional)
- Dark mode support
- Keyboard shortcuts (Arrow keys for navigation)
- Floating navigation buttons with scroll tracking
- Chapter list drawer with auto-scroll to current chapter

**Technology Stack:**
- Vue 3.5+ with TypeScript
- Quasar Framework 2.16+
- Pinia 3.0+ for state management
- Vue Router 4.0+ for navigation
- Axios 1.2+ for HTTP requests
- OpenCC-JS for Chinese text conversion

**State Management:**
- Book metadata (author, title, chapter count)
- All chapters cached in memory (with invalidation logic)
- Current reading position tracking
- Page-based pagination state
- Previous/next chapter navigation

## 🚀 Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for local development)
- Python 3.11+ (for local development)

### Environment Variables

Create a `.env` file in the project root:

```bash
# Backend Configuration
BASE_URL=https://m.xsw.tw
HTTP_TIMEOUT=10
CACHE_TTL_SECONDS=900
CACHE_MAX_ITEMS=500
CHAPTERS_PAGE_SIZE=20
LOG_LEVEL=INFO

# Database
DATABASE_URL=sqlite:///./data/books.db

# Docker Image Configuration
img=xsw
tag=latest

# Python Package Index (if behind corporate firewall)
BASE_URL=https://pypi.org/simple
INDEX_URL=https://pypi.org/simple
TRUSTED_HOST=pypi.org
```

### Build & Deploy

#### Build Backend (API)

```bash
docker compose -f compose.yml -f docker/build.yml up -d xsw --build
```

This builds the FastAPI backend service:
- Exposes port 8000
- Creates persistent volume `xsw_data` for SQLite database
- Mounts `/app/data` for database storage

#### Build Frontend (Web)

```bash
docker compose -f compose.yml -f docker/build.yml up -d web --build
```

This builds the Vue 3 SPA:
- Exposes port 2345 (maps to internal port 80)
- Serves static files via nginx
- Includes built Quasar SPA

#### Build Everything

```bash
docker compose -f compose.yml -f docker/build.yml up -d --build
```

### Access the Application

- **Frontend**: http://localhost:2345
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/xsw/api/docs (Swagger UI)
- **API Health**: http://localhost:8000/xsw/api/health

## 🛠️ Development

### Backend Development

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Run the development server:
```bash
uvicorn main:app --reload --port 8000
```

3. API will be available at:
   - http://localhost:8000/xsw/api/docs (Swagger UI)
   - http://localhost:8000/xsw/api/redoc (ReDoc)

### Frontend Development

1. Install Node.js dependencies:
```bash
npm install
```

2. Run the Quasar dev server:
```bash
npm run dev
```

3. Application will be available at: http://localhost:9000 (default Quasar port)

4. Configure API endpoint in `src/boot/axios.ts`:
```typescript
api.defaults.baseURL = 'http://localhost:8000/xsw/api';
```

### Linting & Formatting

```bash
# Frontend
npm run lint
npm run format

# Backend
black *.py
flake8 *.py
```

## 📂 Project Structure

```
xsw/
├── backend/
│   ├── main.py                 # FastAPI application entry
│   ├── cache_manager.py        # Hybrid cache implementation
│   ├── db_models.py           # SQLAlchemy models
│   ├── db_utils.py            # Database utilities
│   ├── parser.py              # HTML parsing logic
│   └── requirements.txt       # Python dependencies
│
├── frontend/src/
│   ├── boot/                  # Quasar boot files
│   │   ├── axios.ts          # Axios configuration
│   │   ├── appSettings.ts    # App settings
│   │   └── books.ts          # Book store initialization
│   ├── components/           # Vue components
│   │   └── ConfigCard.vue   # Settings dialog
│   ├── layouts/             # Page layouts
│   │   └── MainLayout.vue   # Main app layout
│   ├── pages/               # Route pages
│   │   ├── ChapterPage.vue  # Chapter reading page
│   │   └── ChaptersPage.vue # Chapter list page
│   ├── services/            # Business logic
│   │   ├── bookApi.ts       # API client
│   │   ├── useAppConfig.ts  # App config composable
│   │   └── utils.ts         # Utility functions
│   ├── stores/              # Pinia stores
│   │   ├── appSettings.ts   # App settings store
│   │   └── books.ts         # Book data store
│   ├── types/               # TypeScript types
│   │   └── book-api.ts      # API type definitions
│   └── router/              # Vue Router config
│
├── docker/
│   ├── Dockerfile           # Backend container
│   ├── Dockerfile.web       # Frontend container (nginx)
│   └── build.yml           # Docker Compose build config
│
├── compose.yml             # Main Docker Compose config
├── package.json           # Frontend dependencies
├── quasar.config.ts       # Quasar framework config
└── README.md             # This file
```

## 🔧 Configuration

### Backend Configuration

Modify `.env` or set environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_URL` | `https://m.xsw.tw` | Target scraping site |
| `HTTP_TIMEOUT` | `10` | Default HTTP timeout (seconds) |
| `CACHE_TTL_SECONDS` | `900` | Memory cache TTL (15 minutes) |
| `CACHE_MAX_ITEMS` | `500` | Max items in memory cache |
| `CHAPTERS_PAGE_SIZE` | `20` | Chapters per page |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DATABASE_URL` | `sqlite:///./data/books.db` | Database connection string |

### Frontend Configuration

Modify `src/boot/axios.ts` for API endpoint:

```typescript
api.defaults.baseURL = process.env.API_BASE_URL || '/xsw/api';
api.defaults.timeout = 15000; // Default timeout
```

Modify `quasar.config.ts` for build configuration:

```typescript
build: {
  publicPath: '/xsw/', // Change for different deployment paths
  vueRouterMode: 'hash', // 'hash' or 'history'
}
```

## 📋 API Endpoints

### Book Information
- `GET /xsw/api/books/{book_id}` - Get book metadata
- `GET /xsw/api/books/{book_id}/chapters` - Get chapter list (paginated or all)
  - Query params: `page`, `all`, `nocache`
- `GET /xsw/api/books/{book_id}/chapters/{chapter_num}` - Get chapter content

### Categories
- `GET /xsw/api/categories` - List all categories
- `GET /xsw/api/categories/{cat_id}/books` - Books in category

### Search
- `GET /xsw/api/search?q={query}` - Search books by name/author

### Admin (Cache Management)
- `POST /xsw/api/admin/cache/chapters/page/clear` - Clear page cache
- `POST /xsw/api/admin/cache/chapters/all/clear` - Clear all chapters cache
- `POST /xsw/api/admin/cache/chapters/mapping/clear` - Clear URL mapping cache

### Health
- `GET /xsw/api/health` - Service health check

## 🐛 Troubleshooting

### Database Issues

If you encounter corrupted cache data:

1. Stop the services:
```bash
docker compose down
```

2. Clear the database volume:
```bash
docker volume rm xsw_xsw_data
```

3. Clear backend memory cache via API:
```bash
curl -X POST http://localhost:8000/xsw/api/admin/cache/chapters/all/clear
curl -X POST http://localhost:8000/xsw/api/admin/cache/chapters/page/clear
curl -X POST http://localhost:8000/xsw/api/admin/cache/chapters/mapping/clear
```

4. Restart services:
```bash
docker compose up -d
```

### Timeout Errors

If you experience timeout errors when loading many chapters:

- The backend uses extended timeouts (5 minutes for all chapters)
- Check network connectivity to m.xsw.tw
- Consider using the `nocache` parameter to bypass stale cache: `?nocache=true`

### Navigation Not Working

If prev/next chapter buttons don't work:

- Ensure `currentChapterIndex` is being set in the book store
- Check browser console for navigation errors
- Verify that `allChapters` array is populated

### Dark Mode Styling Issues

If dark mode colors are incorrect:

- Check that Quasar dark mode is enabled in settings
- Verify CSS variables are defined in theme
- Inspect element styles in browser dev tools

## 📦 Production Deployment

### Using Pre-built Images

```bash
# Pull images
docker pull ${img}:${tag}
docker pull ${img}:${tag}-web

# Run with production compose file
docker compose -f compose.yml up -d
```

### Environment-specific Configuration

Create environment-specific `.env` files:

- `.env.development` - Local development
- `.env.staging` - Staging environment
- `.env.production` - Production environment

Load with:
```bash
docker compose --env-file .env.production up -d
```

### Reverse Proxy (nginx)

Example nginx configuration:

```nginx
server {
    listen 80;
    server_name xsw.example.com;

    location / {
        proxy_pass http://localhost:2345;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /xsw/api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }
}
```

## 📄 License

This project is for educational purposes only.

## 🤝 Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📧 Contact

For issues or questions, please open a GitHub issue.
