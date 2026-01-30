/**
 * Base Path Detection Utility
 *
 * Detects the base path at runtime to support serving the app from:
 * - / (root) - Standalone deployment (nginx, dev server)
 * - /spa - FastAPI backend deployment
 * - Custom path - Any other base path
 */

/**
 * Detect the base path from current URL or configuration
 *
 * Detection order:
 * 1. Check config.json basePath setting
 * 2. Auto-detect from window.location
 * 3. Fall back to '/'
 */
export function detectBasePath(configBasePath?: string): string {
  // If explicitly set in config (not 'auto'), use it
  if (configBasePath && configBasePath !== 'auto') {
    return normalizeBasePath(configBasePath);
  }

  // Auto-detect from current URL
  const pathname = window.location.pathname;

  // Check if we're under /spa
  if (pathname.startsWith('/spa')) {
    return '/spa/';
  }

  // Check for other common patterns
  // e.g., /xsw/, /app/, etc.
  const match = pathname.match(/^(\/[^/]+)\//);
  if (match && match[1]) {
    const firstSegment = match[1];

    // Ignore root path
    if (firstSegment === '/') {
      return '/';
    }

    // Known app routes that should NOT be treated as base paths
    const appRoutes = ['/books', '/chapters', '/dashboard'];
    if (!appRoutes.includes(firstSegment)) {
      return firstSegment + '/';
    }
  }

  // Default to root
  return '/';
}

/**
 * Normalize base path to always end with /
 */
function normalizeBasePath(path: string): string {
  if (!path) return '/';
  if (path === '/') return '/';

  // Remove trailing slash if exists, then add it back
  const cleaned = path.replace(/\/$/, '');
  return cleaned + '/';
}

/**
 * Get the full URL with base path
 */
export function getFullPath(path: string, basePath: string): string {
  // Remove leading slash from path
  const cleanPath = path.replace(/^\//, '');

  // Combine base path with route path
  if (basePath === '/') {
    return '/' + cleanPath;
  }

  return basePath + cleanPath;
}

/**
 * Check if current deployment is under a specific base path
 */
export function isUnderBasePath(basePath: string): boolean {
  const normalizedBase = normalizeBasePath(basePath);
  return window.location.pathname.startsWith(normalizedBase.replace(/\/$/, ''));
}

/**
 * Get base path for assets (static files)
 *
 * Assets need to be loaded relative to the base path
 */
export function getAssetPath(assetPath: string, basePath: string): string {
  // Remove leading slash from asset path
  const cleanPath = assetPath.replace(/^\//, '');

  // For root deployment, assets are at /assets/...
  if (basePath === '/') {
    return '/' + cleanPath;
  }

  // For sub-path deployment, assets are at /spa/assets/...
  return basePath + cleanPath;
}

// Export for debugging
export function getBasePathDebugInfo() {
  return {
    pathname: window.location.pathname,
    href: window.location.href,
    detectedBasePath: detectBasePath('auto'),
    isUnderSpa: isUnderBasePath('/spa'),
    isUnderRoot: window.location.pathname === '/' || !window.location.pathname.match(/^\/[^/]+\//),
  };
}
