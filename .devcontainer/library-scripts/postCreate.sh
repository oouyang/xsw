#!/usr/bin/env bash
# postCreate.sh - Runs after the devcontainer is created
# This installs project dependencies and sets up the development environment

set -euo pipefail

echo "🚀 Running postCreate setup for XSW full-stack project..."

# ========================
# Python Backend Setup
# ========================
echo ""
echo "🐍 Setting up Python backend..."

# Verify Python is working
python3 --version || echo "⚠️  Python not found"

# Install Python dependencies
if [ -f requirements.txt ]; then
  echo "📦 Installing Python dependencies from requirements.txt..."
  pip install --user -r requirements.txt || {
    echo "⚠️  Some Python packages failed to install, but continuing..."
  }
else
  echo "⚠️  No requirements.txt found"
fi

# Verify FastAPI and Uvicorn are installed
echo "✅ Verifying Python packages..."
python3 -c "import fastapi, uvicorn" 2>/dev/null && \
  echo "  ✓ FastAPI and Uvicorn installed" || \
  echo "  ⚠️  FastAPI or Uvicorn not found"

# ========================
# Node.js Frontend Setup
# ========================
echo ""
echo "📦 Setting up Node.js frontend..."

# Ensure corepack is enabled (Node 18+ includes it)
echo "📦 Enabling corepack..."
corepack enable || true

# Activate yarn (since project uses yarn.lock)
if [ -f yarn.lock ]; then
  echo "📦 Activating yarn..."
  corepack prepare yarn@stable --activate || true
fi

# Verify npm/yarn can access the network with proper SSL
echo "🔍 Verifying npm registry access..."
npm config get registry || true

# Install project dependencies based on lock file
echo "📦 Installing frontend dependencies..."
if [ -f pnpm-lock.yaml ]; then
  echo "Using pnpm..."
  pnpm install --frozen-lockfile || pnpm install
elif [ -f yarn.lock ]; then
  echo "Using yarn..."
  yarn install --frozen-lockfile || yarn install
elif [ -f package-lock.json ]; then
  echo "Using npm..."
  npm ci || npm install
else
  echo "No lock file found, using npm..."
  npm install
fi

# Verify TypeScript and Quasar are working
echo "✅ Verifying frontend tools..."
npx tsc --version || echo "⚠️  TypeScript not found in project"
npx quasar --version || echo "⚠️  Quasar CLI not found in project"

# ========================
# Database Setup
# ========================
echo ""
echo "💾 Setting up database directory..."
mkdir -p data
echo "  ✓ Created data/ directory for SQLite database"

# ========================
# Display helpful information
# ========================
echo ""
echo "✅ postCreate setup completed successfully!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Backend (FastAPI) commands:"
echo "  uvicorn main_optimized:app --reload --port 8000"
echo "  python main_optimized.py"
echo "  python -m py_compile main_optimized.py  # Syntax check"
echo ""
echo "📝 Frontend (Quasar) commands:"
echo "  npm run dev       - Start Quasar dev server (port 9000)"
echo "  npm run build     - Build for production"
echo "  npm run lint      - Lint code"
echo "  npm run format    - Format code with Prettier"
echo ""
echo "🔧 Database commands:"
echo "  sqlite3 data/xsw_cache.db '.tables'"
echo "  sqlite3 data/xsw_cache.db '.schema books'"
echo ""
echo "🌐 Dev servers:"
echo "  Frontend: http://localhost:9000 (Quasar)"
echo "  Backend:  http://localhost:8000 (FastAPI)"
echo "  API Docs: http://localhost:8000/xsw/api/docs"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
