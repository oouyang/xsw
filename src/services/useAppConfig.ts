import { is_production } from 'src/services/utils';
import { ref, computed } from 'vue';

export interface AppConfig {
  name: string;
  apiBaseUrl: string;
  featureFlags: Record<string, boolean>;
  theme: 'light' | 'dark' | 'auto';
  cacheTimeout: number;
  version?: string | undefined;
  clientId?: string | undefined;
  tenantId?: string | undefined;
  aadRedirectUriBase?: string | undefined;
  hash?: string | undefined;
  me?: string | undefined;
  env?: string | undefined;
  origin?: string | undefined;
  fontsize?: string | undefined;
  dark?: string | undefined;
  page?: string | undefined;
  bookId?: string | undefined;
  chapter?: string | undefined;
  chapters?: string | undefined;
}

const DEFAULT_CONFIG: AppConfig = {
  name: '看小說',
  apiBaseUrl: '/api/',
  featureFlags: {
    isLoading: false,
    prefersDark: true,
  },

  theme: 'light', // default UI theme
  cacheTimeout: 30 * 60 * 1000, // 30 minutes

  clientId: '',
  tenantId: '',
};

// localStorage key
const LS_KEY = 'app.config.overrides';

const _loading = ref(false);
const _loaded = ref(false);
const _error = ref<unknown>(null);
const _config = ref<AppConfig>({ ...DEFAULT_CONFIG });

let _overridesCache: Partial<AppConfig> | undefined;

/* ---------------------------------- utils --------------------------------- */

function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

/** Safely load overrides from localStorage once per session. */
function loadOverridesOnce(): Partial<AppConfig> | undefined {
  if (_overridesCache !== undefined) return _overridesCache;
  if (!isBrowser()) return undefined;
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    _overridesCache = raw ? (JSON.parse(raw) ?? undefined) : undefined;
    // ensure object shape
    if (_overridesCache && typeof _overridesCache !== 'object') {
      _overridesCache = undefined;
    }
  } catch {
    _overridesCache = undefined;
  }
  return _overridesCache;
}

/** Persist overrides (replace cached + localStorage). */
function saveOverrides(newOverrides: Partial<AppConfig>) {
  _overridesCache = newOverrides;
  if (!isBrowser()) return;
  window.localStorage.setItem(LS_KEY, JSON.stringify(newOverrides));
}

/** Defensive number parsing with fallback. */
function toNumberOr(defaultVal: number, v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : defaultVal;
}
/**
 * Helper: parse a JSON-string (e.g. '["A","B"]') into string[].
 * Returns [] on invalid input; trims and uppercases for consistency by default.
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

/** Defensive extraction for fields that should be strings. */
function stringOrUndefined(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined;
}

/** Defensive extraction for theme: defaults to 'light' if unknown. */
function toTheme(v: unknown): AppConfig['theme'] {
  return v === 'dark' || v === 'auto' ? v : 'light';
}

export function useAppConfig() {
  async function load(signal: AbortSignal | null = null) {
    // Prevent duplicate loads
    if (_loaded.value || _loading.value) return;

    _loading.value = true;
    _error.value = null;
    try {
      const res = await fetch('/config.json', { cache: 'no-store', signal });
      if (!res.ok) throw new Error(`Failed to fetch /config.json: ${res.status}`);
      const raw = await res.json();
      const fetchedBase = {
        apiBaseUrl: stringOrUndefined(raw.apiBaseUrl) ?? DEFAULT_CONFIG.apiBaseUrl,
        featureFlags:
          raw.featureFlags && typeof raw.featureFlags === 'object' ? raw.featureFlags : {},
        theme: toTheme(raw.theme),
        cacheTimeout: toNumberOr(DEFAULT_CONFIG.cacheTimeout, raw.cacheTimeout),
      };
      const fetched: Partial<AppConfig> = { ...fetchedBase };

      // ✅ only add optional props when they’re defined
      assignIfDefined(fetched, 'version', stringOrUndefined(raw.version));
      assignIfDefined(fetched, 'clientId', stringOrUndefined(raw.clientId));
      assignIfDefined(fetched, 'tenantId', stringOrUndefined(raw.tenantId));
      assignIfDefined(fetched, 'aadRedirectUriBase', stringOrUndefined(raw.aadRedirectUriBase));

      const overrides = loadOverridesOnce();

      // precedence: DEFAULTS <- fetched <- overrides
      _config.value = mergeConfig({ ...DEFAULT_CONFIG, ...fetched }, overrides);
      _loaded.value = true;
    } catch (e) {
      const overrides = loadOverridesOnce();
      _config.value = mergeConfig({ ...DEFAULT_CONFIG }, overrides);
      _error.value = e;
      _loaded.value = true;

      console.log('load config error ', e);
    } finally {
      _loading.value = false;
    }
  }

  /**
   * Update runtime config and persist to overrides.
   * Only featureFlags is deep-merged; others are shallow.
   */
  function update(partial: Partial<AppConfig>) {
    // Merge into live config
    _config.value = mergeConfig(_config.value, partial);

    // Merge into overrides (single read, single write)
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
    // state
    config: computed(() => _config.value),
    loading: computed(() => _loading.value),
    loaded: computed(() => _loaded.value),
    error: computed(() => _error.value),
    // actions
    initAppConfig,
    load,
    update,
    resetOverrides,
  };
}

const {
  VITE_GIT_COMMIT_HASH: hash,
  VITE_AAD_REDIRECT_URI_BASE: base,
  VITE_AAD_CLIENTID: client_id,
  VITE_AAD_TENANT_ID: tenant_id,
  VITE_API_BASE: api_base,
} = import.meta.env;

/**
 * Initialize environment-derived fields first,
 * then hydrate remote config (which can override defaults).
 */
export async function initAppConfig() {
  const appConfig = useAppConfig();

  const env = is_production() ? 'production' : 'development';
  // Build overrides without undefineds
  const runtimeOverrides: Partial<AppConfig> = {
    env, // required value; not undefined
    apiBaseUrl: stringOrUndefined(api_base) ?? DEFAULT_CONFIG.apiBaseUrl,
  };
  assignIfDefined(runtimeOverrides, 'hash', stringOrUndefined(hash));
  assignIfDefined(runtimeOverrides, 'clientId', stringOrUndefined(client_id));
  assignIfDefined(runtimeOverrides, 'tenantId', stringOrUndefined(tenant_id));
  assignIfDefined(runtimeOverrides, 'aadRedirectUriBase', stringOrUndefined(base));

  appConfig.update(runtimeOverrides);

  // Load remote config.json with an AbortController (optional)
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : undefined;
  await appConfig.load(controller?.signal ?? null);
}
