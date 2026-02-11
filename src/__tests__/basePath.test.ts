import { describe, it, expect, beforeEach } from 'vitest';
import { detectBasePath, getFullPath, getAssetPath } from 'src/utils/basePath';

// Helper to mock window.location.pathname
function setPathname(pathname: string) {
  Object.defineProperty(window, 'location', {
    value: { ...window.location, pathname },
    writable: true,
    configurable: true,
  });
}

// ──────────────────────────────────────────────────────────────
// detectBasePath
// ──────────────────────────────────────────────────────────────
describe('detectBasePath', () => {
  beforeEach(() => {
    setPathname('/');
  });

  it('returns explicit path when not "auto"', () => {
    expect(detectBasePath('/my-app')).toBe('/my-app/');
  });

  it('normalizes explicit path with trailing slash', () => {
    expect(detectBasePath('/my-app/')).toBe('/my-app/');
  });

  it('detects /spa base path in auto mode', () => {
    setPathname('/spa/some/page');
    expect(detectBasePath('auto')).toBe('/spa/');
  });

  it('detects custom sub-path in auto mode', () => {
    setPathname('/custom/some/page');
    expect(detectBasePath('auto')).toBe('/custom/');
  });

  it('ignores known app routes like /books', () => {
    setPathname('/books/some-id');
    expect(detectBasePath('auto')).toBe('/');
  });

  it('ignores known app routes like /book', () => {
    setPathname('/book/abc123');
    expect(detectBasePath('auto')).toBe('/');
  });

  it('ignores known app routes like /cate', () => {
    setPathname('/cate/fantasy');
    expect(detectBasePath('auto')).toBe('/');
  });

  it('returns / for root path', () => {
    setPathname('/');
    expect(detectBasePath('auto')).toBe('/');
  });

  it('returns / when configBasePath is undefined', () => {
    setPathname('/');
    expect(detectBasePath(undefined)).toBe('/');
  });
});

// ──────────────────────────────────────────────────────────────
// getFullPath
// ──────────────────────────────────────────────────────────────
describe('getFullPath', () => {
  it('prepends / for root base', () => {
    expect(getFullPath('books/123', '/')).toBe('/books/123');
  });

  it('prepends sub-base path', () => {
    expect(getFullPath('books/123', '/spa/')).toBe('/spa/books/123');
  });

  it('handles path with leading slash', () => {
    expect(getFullPath('/books/123', '/spa/')).toBe('/spa/books/123');
  });
});

// ──────────────────────────────────────────────────────────────
// getAssetPath
// ──────────────────────────────────────────────────────────────
describe('getAssetPath', () => {
  it('prepends / for root base', () => {
    expect(getAssetPath('assets/logo.png', '/')).toBe('/assets/logo.png');
  });

  it('prepends sub-base path', () => {
    expect(getAssetPath('assets/logo.png', '/spa/')).toBe('/spa/assets/logo.png');
  });

  it('handles asset path with leading slash', () => {
    expect(getAssetPath('/icons/favicon.ico', '/spa/')).toBe('/spa/icons/favicon.ico');
  });
});
