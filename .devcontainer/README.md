# DevContainer Setup for XSW (看小說)

This devcontainer configuration provides a fully configured development environment for the XSW full-stack project with proper support for Micron's corporate network environment.

## Project Overview

**XSW (看小說)** is a Chinese novel reading platform with:
- **Backend**: FastAPI (Python 3.11) with SQLite database caching
- **Frontend**: Vue 3 + Quasar framework
- **Architecture**: Single-container deployment with SPA serving

## Features

### 🔐 Security & Networking
- **Corporate Proxy Support**: Pre-configured for Micron's proxy (proxy-web.micron.com:80)
- **SSL/TLS Certificates**: Micron Root and Issuing CA certificates properly installed
- **Certificate Bundle**: Combined CA bundle for Node.js (`NODE_EXTRA_CA_CERTS`) and Python (`REQUESTS_CA_BUNDLE`)
- **No SSL Verification Disabled**: Proper certificate chain validation maintained

### 🛠️ Development Tools

#### Backend (Python)
- **Python 3.11**: With pip and virtualenv support
- **FastAPI**: High-performance async web framework
- **Uvicorn**: ASGI server with hot reload
- **SQLite3**: Command-line tools for database inspection
- **Ruff**: Fast Python linter and formatter

#### Frontend (Node.js)
- **Node.js 20**: LTS version with Corepack enabled
- **Yarn**: Automatically activated for dependency management
- **TypeScript**: Full TypeScript support with Vue 3
- **Quasar**: Vue 3 framework with Material Design components
- **Vite**: Fast development server
- **Git**: With bash completion and GitLens extension

### 🎨 VS Code Extensions
- **Python**: ms-python.python, ms-python.vscode-pylance
- **Ruff**: charliermarsh.ruff (Python linting and formatting)
- **Vue**: Vue.volar, Vue.vscode-typescript-vue-plugin
- **Prettier**: Code formatting
- **ESLint**: Code linting
- **Error Lens**: Inline error display
- **GitLens**: Git integration
- **Docker**: ms-azuretools.vscode-docker
- **REST Client**: humao.rest-client (for API testing)

### 🚀 Performance Optimizations
- **Persistent Volumes**: Caches for npm, yarn, pip, and ruff
- **Shared Memory**: 2GB allocated for potential browser testing
- **Docker Buildx**: For multi-platform builds

## Quick Start

### 1. Prerequisites
- Docker Desktop or Docker Engine
- VS Code with Remote-Containers extension
- Access to Micron network (for proxy and CA certificates)

### 2. Open in DevContainer
```bash
# Method 1: VS Code Command Palette
# Press F1 or Ctrl+Shift+P
# Type: "Dev Containers: Reopen in Container"

# Method 2: CLI
code --folder-uri vscode-remote://dev-container+${PWD}
```

### 3. Wait for Setup
The container will:
1. Build the Docker image with Python 3.11 + Node.js 20
2. Install Micron CA certificates
3. Run `postCreate.sh` to install dependencies
   - Python packages from requirements.txt
   - npm/yarn packages from package.json
4. Create data/ directory for SQLite database

### 4. Start Development

#### Backend (FastAPI)
```bash
# Start backend server with hot reload
uvicorn main_optimized:app --reload --port 8000

# Or run directly
python main_optimized.py

# Syntax check
python -m py_compile main_optimized.py
```

Access API documentation at: http://localhost:8000/xsw/api/docs

#### Frontend (Quasar)
```bash
# Start Quasar dev server
npm run dev    # Opens at http://localhost:9000

# Type check
npm run tsc

# Format code
npm run format

# Lint code
npm run lint

# Build for production
npm run build
```

#### Database Operations
```bash
# Open SQLite database
sqlite3 data/xsw_cache.db

# List tables
sqlite3 data/xsw_cache.db '.tables'

# View schema
sqlite3 data/xsw_cache.db '.schema books'

# Query data
sqlite3 data/xsw_cache.db 'SELECT COUNT(*) FROM books;'
```

## Architecture

### File Structure
```
.devcontainer/
├── devcontainer.json         # Main configuration
├── Dockerfile               # Container image definition (Python 3.11 + Node.js 20)
├── library-scripts/
│   ├── install.sh          # Docker CLI installation (build-time)
│   └── postCreate.sh       # Dependency installation (runtime)
└── README.md               # This file
```

### Build Process

#### 1. Dockerfile (Build Time)
The Dockerfile runs as `root` and performs system-level setup:

**Base Image**: Microsoft's Python 3.11 devcontainer image

**Step 1: CA Certificate Installation**
```dockerfile
# Fetches Micron Root and Issuing CA from PKI server
# Installs them to /usr/local/share/ca-certificates/micron/
# Runs update-ca-certificates to add to system trust store
```

**Step 2: CA Bundle Creation**
```dockerfile
# Combines both certificates into ca-bundle.crt
# This bundle is used by NODE_EXTRA_CA_CERTS and REQUESTS_CA_BUNDLE
```

**Step 3: Node.js Installation**
```dockerfile
# Installs Node.js 20 LTS via NodeSource repository
# Enables corepack for yarn/pnpm management
```

**Step 4: System Dependencies**
- CLI tools: vim, git, curl, jq, bash-completion
- SQLite3: Database inspection tools
- Python build tools: build-essential, python3-dev
- Locale configuration: en_US.UTF-8

**Step 5: Custom Scripts**
- Executes `install.sh` to install Docker CLI tools
- Skips `postCreate.sh` (runs after container starts)

#### 2. postCreate.sh (Runtime)
Runs as `vscode` user after container creation:

**Backend Setup**
- Installs Python packages from requirements.txt
- Verifies FastAPI and Uvicorn installation
- Creates data/ directory for SQLite database

**Frontend Setup**
- Enables corepack and activates yarn
- Installs npm packages from package.json/yarn.lock
- Verifies TypeScript and Quasar installation

**Helpful Output**
- Displays available commands
- Shows dev server URLs

## Environment Variables

### Build-Time (Dockerfile ARGs)
```dockerfile
HTTP_PROXY=http://proxy-web.micron.com:80
HTTPS_PROXY=http://proxy-web.micron.com:80
NO_PROXY=localhost,127.0.0.1,.micron.com
```

### Runtime (Container ENV)
```bash
# Proxy configuration
HTTP_PROXY=http://proxy-web.micron.com:80
HTTPS_PROXY=http://proxy-web.micron.com:80
NO_PROXY=localhost,127.0.0.1,.micron.com

# SSL/TLS certificate paths
NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/micron/ca-bundle.crt
REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
NODE_OPTIONS=--use-openssl-ca

# Python configuration
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1

# Remote Docker access (optional)
DOCKER_HOST=ssh://hpcadmin@bolhpcnifi02

# Locale
LANG=en_US.UTF-8
LC_ALL=en_US.UTF-8
```

## Persistent Volumes

The devcontainer uses Docker volumes to cache data between rebuilds:

```json
{
  "mounts": [
    "xsw-node-cache",     // General Node.js cache
    "xsw-npm-cache",      // npm global cache
    "xsw-yarn-cache",     // Yarn cache
    "xsw-pip-cache",      // Python pip cache
    "xsw-ruff-cache",     // Ruff linter cache
    "xsw-data"            // SQLite database and application data
  ]
}
```

**Benefits:**
- Faster container rebuilds
- Reduced network traffic
- Persistent database data
- Persistent package caches

## Ports

| Port | Service | Purpose |
|------|---------|---------|
| 8000 | FastAPI Backend | REST API endpoints |
| 9000 | Quasar Dev Server | Vue 3 frontend with hot reload |

Both ports are automatically forwarded and will notify you when the servers start.

## Troubleshooting

### SSL Certificate Errors

**Symptom:**
```
npm ERR! self signed certificate in certificate chain
pip error: SSL: CERTIFICATE_VERIFY_FAILED
```

**Solution:**
1. Verify CA certificates are installed:
   ```bash
   ls -la /usr/local/share/ca-certificates/micron/
   # Should show: Micron_Root_CA.crt, Micron_Issuing_CA.crt, ca-bundle.crt
   ```

2. Check environment variables:
   ```bash
   echo $NODE_EXTRA_CA_CERTS
   echo $REQUESTS_CA_BUNDLE
   echo $NODE_OPTIONS
   ```

3. Verify system trust store:
   ```bash
   update-ca-certificates --verbose
   ```

### Proxy Connection Issues

**Symptom:**
```
npm ERR! network request failed
requests.exceptions.ProxyError
```

**Solution:**
1. Verify proxy environment variables:
   ```bash
   env | grep -i proxy
   ```

2. Test proxy connectivity:
   ```bash
   # Test npm registry
   curl -v -x http://proxy-web.micron.com:80 https://registry.npmjs.org

   # Test PyPI
   curl -v -x http://proxy-web.micron.com:80 https://pypi.org/simple/
   ```

3. Check NO_PROXY exclusions for local services

### Python Package Installation Fails

**Symptom:**
```
pip install fails with compilation errors
```

**Solution:**
1. Verify build tools are installed:
   ```bash
   gcc --version
   python3-config --includes
   ```

2. Install package with verbose output:
   ```bash
   pip install --user --verbose package-name
   ```

3. Check if package has binary wheels available:
   ```bash
   pip install --only-binary :all: package-name
   ```

### Node Package Installation Fails

**Symptom:**
```
yarn install fails with node-gyp errors
```

**Solution:**
1. Clear caches:
   ```bash
   yarn cache clean
   rm -rf node_modules
   yarn install
   ```

2. Verify Node.js version:
   ```bash
   node --version  # Should be 20.x
   ```

### Container Build Fails

**Symptom:**
```
ERROR: failed to solve: process "/bin/sh -c ..." did not complete successfully
```

**Solution:**
1. Check if behind corporate proxy:
   ```bash
   # Verify proxy is set in devcontainer.json build.args
   ```

2. Rebuild without cache:
   ```bash
   # In VS Code: "Dev Containers: Rebuild Container Without Cache"
   ```

3. Check Docker build logs for specific error

### Database Locked Error

**Symptom:**
```
sqlite3.OperationalError: database is locked
```

**Solution:**
1. Close all connections to the database
2. Check for zombie processes:
   ```bash
   lsof data/xsw_cache.db
   ```
3. Restart the backend server

## Development Workflow

### Typical Development Session

1. **Open in DevContainer**
   - VS Code Command Palette: "Dev Containers: Reopen in Container"

2. **Start Backend** (Terminal 1)
   ```bash
   uvicorn main_optimized:app --reload --port 8000
   ```

3. **Start Frontend** (Terminal 2)
   ```bash
   npm run dev
   ```

4. **Make Changes**
   - Edit Python files → Backend auto-reloads
   - Edit Vue files → Frontend hot-reloads

5. **Test APIs**
   - Open http://localhost:8000/xsw/api/docs
   - Or use REST Client extension

6. **Format Code**
   ```bash
   # Backend (Python)
   ruff format .
   ruff check --fix .

   # Frontend (TypeScript/Vue)
   npm run format
   npm run lint
   ```

## Customization

### Adding VS Code Extensions

Edit `.devcontainer/devcontainer.json`:
```json
{
  "customizations": {
    "vscode": {
      "extensions": [
        "Vue.volar",
        "your.extension-id"  // Add here
      ]
    }
  }
}
```

### Adding System Packages

Edit `.devcontainer/Dockerfile`:
```dockerfile
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      your-package-name; \
    rm -rf /var/lib/apt/lists/*
```

### Adding Python Packages

Add to `requirements.txt` and rebuild:
```bash
echo "new-package>=1.0.0" >> requirements.txt
pip install --user -r requirements.txt
```

### Adding Node Packages

```bash
yarn add package-name
# or
npm install package-name
```

### Changing Python Version

Edit `.devcontainer/Dockerfile`:
```dockerfile
FROM mcr.microsoft.com/devcontainers/python:3.12  # Change from 3.11 to 3.12
```

### Changing Node Version

Edit `.devcontainer/Dockerfile`:
```dockerfile
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash -;  # Change from 20.x to 22.x
```

## Security Best Practices

### ✅ What We Do Right
1. **Use Official Base Images**: Microsoft's devcontainer images
2. **Proper CA Chain**: System-level certificate installation
3. **No SSL Verification Disabled**: All tools use proper certificates
4. **Non-Root User**: Runs as `vscode` user after setup
5. **Minimal Attack Surface**: Only necessary packages installed
6. **Layer Caching**: Efficient Docker layer structure

### ❌ What We Avoid
1. ~~`npm config set strict-ssl false`~~ (NEVER disable SSL verification)
2. ~~`NODE_TLS_REJECT_UNAUTHORIZED=0`~~ (NEVER disable TLS validation)
3. ~~`pip install --trusted-host`~~ (NEVER skip certificate verification)
4. ~~Installing as root~~ (Switch to vscode user after system setup)

## Performance Tips

1. **Use Volume Mounts**: Already configured for caches
2. **BuildKit**: Enabled by default in Docker 20.10+
3. **Layer Optimization**: Frequently changing layers are at the bottom
4. **Parallel Installs**: Both pip and yarn use parallel downloads
5. **Hot Reload**: Both backend and frontend support live reload

## Remote Docker Access

The devcontainer includes Docker CLI for accessing a remote Docker daemon:

```bash
# Set in devcontainer.json
DOCKER_HOST=ssh://hpcadmin@bolhpcnifi02

# Usage
docker ps                    # Lists containers on remote host
docker build -t myimage .    # Builds on remote Docker daemon
docker compose up -d          # Runs compose on remote host
```

**Note**: Requires SSH key authentication to remote host.

## Project-Specific Notes

### Authentication
The backend supports Google OAuth2 SSO and password authentication. Authentication can be disabled for development:

```bash
# In .env file
AUTH_ENABLED=false
```

### Database
The project uses SQLite with a 3-tier caching architecture:
1. Memory cache (TTL-based)
2. SQLite database (persistent)
3. Web scraping (fallback)

### Sync Scripts
The project includes sync scripts for bulk operations:
- `sync_categories.sh` - Sync book categories
- `sync_books.sh` - Sync book metadata
- `sync_content_enhanced.sh` - Sync chapter content

These run with rate limiting to avoid being blocked by the origin site.

## References

- [VS Code DevContainers](https://code.visualstudio.com/docs/devcontainers/containers)
- [Microsoft DevContainer Images](https://github.com/devcontainers/images)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Quasar Framework](https://quasar.dev/)
- [Vue 3 Documentation](https://vuejs.org/)
- [Node.js SSL/TLS Options](https://nodejs.org/api/cli.html#node_optionsoptions)
- [Python Requests SSL](https://requests.readthedocs.io/en/latest/user/advanced/#ssl-cert-verification)

## Changelog

### 2026-02-02 - Full-Stack Configuration
- Changed project name from "eps_padlog_frontend" to "xsw-fullstack"
- Added Python 3.11 support alongside Node.js 20
- Changed base image from typescript-node to python devcontainer
- Added Python VS Code extensions (ms-python.python, charliermarsh.ruff)
- Added SQLite3 tools for database operations
- Updated ports: 9000 (Quasar frontend) and 8000 (FastAPI backend)
- Added Python cache volumes (pip, ruff)
- Updated postCreate.sh to install both Python and Node.js dependencies
- Added database directory creation
- Changed user from 'node' to 'vscode' (Python base image convention)
- Added REST Client extension for API testing
- Added Docker extension for container management
- Updated documentation for full-stack development workflow

### 2024-02-02 - Original Frontend Setup
- Fixed JSON syntax errors in devcontainer.json
- Created proper CA bundle (ca-bundle.crt) for NODE_EXTRA_CA_CERTS
- Removed insecure SSL verification disabling
- Updated Docker CLI to v24.0.7
- Improved error handling in postCreate.sh
- Added comprehensive documentation
- Increased shared memory to 2GB
- Added project-specific volume names
