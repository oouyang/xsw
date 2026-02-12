import { is_production } from 'src/services/utils';
import type { SupportedLocale } from 'src/stores/appSettings';
import { ref, computed } from 'vue';

// ============================================================================
// TYPES & INTERFACES
// ============================================================================

/**
 * Application configuration with priority system:
 * DEFAULTS <- envOverrides <- config.json <- userOverrides (localStorage)
 */
export interface AppConfig {
  // Core application settings
  name: string;
  apiBaseUrl: string;
  theme: 'light' | 'dark' | 'auto';
  cacheTimeout: number;
  featureFlags: Record<string, boolean>;

  // Optional: User preferences (runtime)
  locale?: SupportedLocale;
  fontsize?: string;
  dark?: string;

  // Optional: Navigation state (runtime)
  page?: string;
  bookId?: string;
  chapter?: string;
  chapters?: string;

  // Optional: Authentication & environment (build-time/config.json)
  version?: string;
  clientId?: string;
  tenantId?: string;
  aadRedirectUriBase?: string;
  hash?: string;
  env?: string;

  // Optional: Social login provider client IDs (config.json)
  googleClientId?: string;
  facebookAppId?: string;
  appleClientId?: string;
  wechatAppId?: string;

  // Optional: Legacy/internal
  me?: string;
  origin?: string;
}

// ============================================================================
// CONSTANTS
// ============================================================================

/** Cache duration in milliseconds (30 minutes) */
const CACHE_TIMEOUT_MS = 30 * 60 * 1000;

/** LocalStorage key for user overrides */
const LS_KEY = 'app.config.overrides';

/** Default application configuration */
const DEFAULT_CONFIG: AppConfig = {
  // Core settings
  name: '看小說',
  apiBaseUrl: '/xsw/api', // Relative path as default fallback
  theme: 'dark',
  cacheTimeout: CACHE_TIMEOUT_MS,
  featureFlags: {
    isLoading: false,
    prefersDark: true,
  },

  // User preferences
  locale: 'zh-TW',
  fontsize: '5',
  dark: 'true',

  // Authentication (empty defaults)
  clientId: '',
  tenantId: '',
};

// ============================================================================
// STATE MANAGEMENT
// ============================================================================

/** Loading state: true while fetching config.json */
const _loading = ref(false);

/** Loaded state: true after first successful or failed load attempt */
const _loaded = ref(false);

/** Error state: contains error if config.json fetch failed */
const _error = ref<unknown>(null);

/** Current application configuration (merged from all sources) */
const _config = ref<AppConfig>({ ...DEFAULT_CONFIG });

/** In-memory cache of localStorage overrides (loaded once per session) */
let _overridesCache: Partial<AppConfig> | undefined;

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

// --------------------------- Browser Detection ------------------------------

/** Check if running in browser environment with localStorage available */
function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

// ----------------------- LocalStorage Management ----------------------------

/**
 * Load user overrides from localStorage (cached for session).
 * Returns undefined if not in browser or if localStorage is empty/invalid.
 */
function loadOverridesOnce(): Partial<AppConfig> | undefined {
  if (_overridesCache !== undefined) return _overridesCache;
  if (!isBrowser()) return undefined;

  try {
    const raw = window.localStorage.getItem(LS_KEY);
    _overridesCache = raw ? (JSON.parse(raw) ?? undefined) : undefined;

    // Ensure object shape
    if (_overridesCache && typeof _overridesCache !== 'object') {
      _overridesCache = undefined;
    }
  } catch {
    _overridesCache = undefined;
  }

  return _overridesCache;
}

/**
 * Save user overrides to localStorage and update session cache.
 * Does nothing if not in browser environment.
 */
function saveOverrides(newOverrides: Partial<AppConfig>) {
  _overridesCache = newOverrides;
  if (!isBrowser()) return;
  window.localStorage.setItem(LS_KEY, JSON.stringify(newOverrides));
}

// ----------------------- Type-Safe Parsing ----------------------------------

/** Safely parse number with fallback for invalid values */
function toNumberOr(defaultVal: number, v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : defaultVal;
}

/** Safely extract string or return undefined */
function stringOrUndefined(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined;
}

/** Safely extract theme value with fallback to 'light' */
function toTheme(v: unknown): AppConfig['theme'] {
  return v === 'dark' || v === 'auto' ? v : 'light';
}

/**
 * Parse JSON string array (e.g., '["A","B"]') into string[].
 * Returns [] on invalid input. Optionally trims and uppercases.
 */
export function getJsonStringArray(jsonString?: string, opts?: { upper?: boolean }): string[] {
  if (!jsonString) return [];

  try {
    const parsed = JSON.parse(jsonString);
    if (!Array.isArray(parsed)) return [];

    return parsed
      .map((s) => (typeof s === 'string' ? s.trim() : ''))
      .filter(Boolean)
      .map((s) => (opts?.upper ? s.toUpperCase() : s));
  } catch {
    return [];
  }
}

// ----------------------- Object Manipulation --------------------------------

/**
 * Assign value to target object only if value is defined.
 * Prevents setting undefined properties in merged configs.
 */
function assignIfDefined<T extends object, K extends keyof T>(
  target: T,
  key: K,
  value: unknown,
): asserts target is T & Record<K, unknown> {
  if (value !== undefined) {
    // @ts-expect-error index signature assignment for dynamic keys
    target[key] = value;
  }
}

/**
 * Deep merge configuration objects.
 * FeatureFlags are deep-merged; all other properties are shallow-merged.
 *
 * @param base - Base configuration
 * @param overrides - Partial overrides to apply
 * @returns Merged configuration
 */
function mergeConfig(base: AppConfig, overrides?: Partial<AppConfig>): AppConfig {
  if (!overrides) return base;

  const merged: AppConfig = {
    ...base,
    ...overrides,
    featureFlags: {
      ...base.featureFlags,
      ...(overrides.featureFlags || {}),
    },
  };

  return merged;
}

// ============================================================================
// COMPOSABLE: useAppConfig
// ============================================================================

/**
 * Main composable for application configuration management.
 * Provides reactive config state and methods to load, update, and reset config.
 *
 * Configuration Priority (lowest to highest):
 * 1. DEFAULT_CONFIG (hardcoded defaults)
 * 2. envOverrides (build-time environment variables)
 * 3. config.json (remote configuration file)
 * 4. userOverrides (localStorage - user's runtime changes)
 */
export function useAppConfig() {
  /**
   * Load configuration from /config.json and merge with all sources.
   *
   * @param signal - AbortSignal for cancelling fetch request
   * @param envOverrides - Build-time environment variables (lower priority than config.json)
   */
  async function load(signal: AbortSignal | null = null, envOverrides?: Partial<AppConfig>) {
    // Prevent duplicate loads
    if (_loaded.value || _loading.value) return;

    _loading.value = true;
    _error.value = null;

    try {
      // Fetch remote configuration
      const res = await fetch('/config.json', { cache: 'no-store', signal });
      if (!res.ok) throw new Error(`Failed to fetch /config.json: ${res.status}`);
      const raw = await res.json();

      // Parse and validate config.json fields
      const fetchedBase = {
        apiBaseUrl: stringOrUndefined(raw.apiBaseUrl) ?? DEFAULT_CONFIG.apiBaseUrl,
        featureFlags:
          raw.featureFlags && typeof raw.featureFlags === 'object' ? raw.featureFlags : {},
        theme: toTheme(raw.theme),
        cacheTimeout: toNumberOr(DEFAULT_CONFIG.cacheTimeout, raw.cacheTimeout),
      };
      const fetched: Partial<AppConfig> = { ...fetchedBase };

      // Add optional fields only if defined
      assignIfDefined(fetched, 'version', stringOrUndefined(raw.version));
      assignIfDefined(fetched, 'clientId', stringOrUndefined(raw.clientId));
      assignIfDefined(fetched, 'tenantId', stringOrUndefined(raw.tenantId));
      assignIfDefined(fetched, 'aadRedirectUriBase', stringOrUndefined(raw.aadRedirectUriBase));

      // Load user's localStorage overrides
      const userOverrides = loadOverridesOnce();

      // Merge all sources with correct priority
      // Priority: DEFAULTS <- envOverrides <- config.json <- userOverrides
      let merged = { ...DEFAULT_CONFIG };
      if (envOverrides) {
        merged = mergeConfig(merged, envOverrides);
      }
      merged = mergeConfig(merged, fetched);
      _config.value = mergeConfig(merged, userOverrides);

      _loaded.value = true;
    } catch (e) {
      // Fallback if config.json fails: use DEFAULTS + envOverrides + userOverrides
      const userOverrides = loadOverridesOnce();
      let merged = { ...DEFAULT_CONFIG };
      if (envOverrides) {
        merged = mergeConfig(merged, envOverrides);
      }
      _config.value = mergeConfig(merged, userOverrides);

      _error.value = e;
      _loaded.value = true;

      console.log('load config error ', e);
    } finally {
      _loading.value = false;
    }
  }

  /**
   * Update runtime configuration and persist changes to localStorage.
   * Changes are merged with existing userOverrides.
   *
   * Note: Only featureFlags are deep-merged; other properties are shallow-merged.
   *
   * @param partial - Partial configuration to update
   */
  function update(partial: Partial<AppConfig>) {
    // Update live config immediately
    _config.value = mergeConfig(_config.value, partial);

    // Merge with existing localStorage overrides and save
    const currentOverrides = loadOverridesOnce() || {};
    const nextOverrides: Partial<AppConfig> = {
      ...currentOverrides,
      ...partial,
      featureFlags: {
        ...(currentOverrides.featureFlags || {}),
        ...(partial.featureFlags || {}),
      },
    };
    saveOverrides(nextOverrides);
  }

  /**
   * Reset all user overrides and restore default configuration.
   * Clears localStorage and resets all reactive state.
   */
  function resetOverrides() {
    if (isBrowser()) {
      window.localStorage.removeItem(LS_KEY);
    }
    _overridesCache = undefined;
    _config.value = { ...DEFAULT_CONFIG };
    _loaded.value = false;
    _error.value = null;
    _loading.value = false;
  }

  return {
    // Reactive state (read-only)
    config: computed(() => _config.value),
    loading: computed(() => _loading.value),
    loaded: computed(() => _loaded.value),
    error: computed(() => _error.value),

    // Actions
    initAppConfig,
    load,
    update,
    resetOverrides,
  };
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/** Extract Vite environment variables */
const {
  VITE_GIT_COMMIT_HASH: hash,
  VITE_AAD_REDIRECT_URI_BASE: base,
  VITE_AAD_CLIENTID: client_id,
  VITE_AAD_TENANT_ID: tenant_id,
  VITE_API_BASE: api_base,
} = import.meta.env;

/**
 * Initialize application configuration at startup.
 *
 * This function:
 * 1. Extracts build-time environment variables
 * 2. Performs migration cleanup (removes old localStorage keys)
 * 3. Loads config.json with proper priority merging
 *
 * Configuration Priority (lowest to highest):
 * - DEFAULT_CONFIG (hardcoded defaults)
 * - envOverrides (build-time Vite env vars)
 * - config.json (remote configuration)
 * - userOverrides (localStorage - runtime user changes)
 *
 * This ensures config.json can override build settings, but users
 * can still override both via localStorage.
 */
export async function initAppConfig() {
  const appConfig = useAppConfig();

  // Migration: Clean up old apiBaseUrl override if no env var is set
  // Allows config.json to take precedence for existing users
  if (!api_base && isBrowser()) {
    const currentOverrides = loadOverridesOnce();
    if (currentOverrides?.apiBaseUrl) {
      console.log(
        '[initAppConfig] Removing old apiBaseUrl override to let config.json take precedence:',
        currentOverrides.apiBaseUrl,
      );
      const { ...rest } = currentOverrides;
      saveOverrides(rest);
      // Force reload overrides cache
      _overridesCache = rest;
    }
  }

  // Determine environment
  const env = is_production() ? 'production' : 'development';

  // Build environment overrides from Vite variables
  // Note: These have LOWER priority than config.json
  const envOverrides: Partial<AppConfig> = {
    env, // Always set environment
  };

  // Add optional build-time variables if provided
  assignIfDefined(envOverrides, 'apiBaseUrl', stringOrUndefined(api_base));
  assignIfDefined(envOverrides, 'hash', stringOrUndefined(hash));
  assignIfDefined(envOverrides, 'clientId', stringOrUndefined(client_id));
  assignIfDefined(envOverrides, 'tenantId', stringOrUndefined(tenant_id));
  assignIfDefined(envOverrides, 'aadRedirectUriBase', stringOrUndefined(base));

  // Load and merge all configuration sources
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : undefined;
  await appConfig.load(controller?.signal ?? null, envOverrides);
}
