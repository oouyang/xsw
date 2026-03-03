# Bus OTA (Over-The-Air) Static Bundle Guide

## Overview

The OTA system allows the frontend to download static bus data (routes, stops, shapes) once and use it offline. Only real-time data (arrivals, positions) needs to be polled from the API.

**Benefits**:
- 📉 **Reduced API calls**: 99% reduction in requests for static data
- 🚀 **Faster load times**: Instant route/stop lookup from localStorage
- 💾 **Offline capable**: Works without internet for static data
- 💰 **Lower costs**: Stays well within TDX free tier

---

## Architecture

```
┌──────────────┐
│  Frontend    │
│  (Vue 3)     │
└──────┬───────┘
       │
       ├─── Check version
       │    GET /bus/api/bundle/version
       │
       ├─── Download if outdated
       │    GET /bus/api/bundle/download
       │    (2-5MB gzipped)
       │
       └─── Poll real-time only
            GET /bus/api?estime&709
            GET /bus/api?mapbus&709

┌──────────────┐
│   Backend    │
│  (FastAPI)   │
└──────┬───────┘
       │
       ├─── Weekly cron job
       │    scripts/generate_bus_bundle.py
       │
       └─── Serve bundle
            static/bus/bundle.json.gz
```

---

## Bundle Structure

```json
{
  "version": "2026-03-03-1200",
  "generated_at": "2026-03-03T12:00:00",
  "cities": {
    "Taoyuan": {
      "routes": {
        "709": {
          "name": "709",
          "from": "平鎮分局",
          "to": "永寧轉運站",
          "stops": {
            "0": [
              {
                "id": "TAO6116",
                "name": "平鎮分局",
                "lat": 24.9515,
                "lng": 121.2168,
                "seq": 1
              },
              {
                "id": "TAO6120",
                "name": "平南國中",
                "lat": 24.9523,
                "lng": 121.2175,
                "seq": 2
              }
            ],
            "1": [...]
          },
          "shapes": {
            "0": [[121.2168, 24.9515], [121.2175, 24.9523], ...],
            "1": [...]
          }
        },
        "710": {...}
      }
    },
    "Taipei": {...}
  },
  "stats": {
    "total_cities": 1,
    "total_routes": 50,
    "total_stops": 1234
  }
}
```

---

## Backend Setup

### 1. Generate Bundle Manually

```bash
# Single city (Taoyuan)
python3 scripts/generate_bus_bundle.py --city Taoyuan

# Multiple cities
python3 scripts/generate_bus_bundle.py --city Taoyuan --city Taipei

# All Taiwan cities (WARNING: Takes ~30 minutes, ~50MB)
python3 scripts/generate_bus_bundle.py --all

# Custom output path
python3 scripts/generate_bus_bundle.py --output /path/to/bundle.json.gz
```

**Output**:
```
Processing city: Taoyuan
  Found 150 routes
  Processed 10/50 routes
  Processed 20/50 routes
  ...
  Taoyuan: 50 routes, 1234 stops

Bundle generated successfully!
  Version: 2026-03-03-1200
  Cities: 1
  Routes: 50
  Stops: 1234

Saved to: static/bus/bundle.json.gz
  Uncompressed: 2456.3 KB
  Compressed: 523.7 KB
  Compression: 78.7%
```

### 2. Setup Weekly Cron Job

```bash
# Run setup script
./scripts/setup_bundle_cron.sh

# Output:
# ✓ Cron job added successfully
# Cron job will run:
#   - Every Sunday at 2:00 AM
#   - Logs: /opt/ws/xsw/logs/bus_bundle.log
```

**Cron Schedule**:
- **Sunday 2:00 AM**: Weekly regeneration (low traffic time)
- **Logs**: Automatically logged to `logs/bus_bundle.log`

### 3. Verify Bundle Endpoints

```bash
# Check version
curl http://localhost:8000/bus/api/bundle/version

# Response:
{
  "version": "2026-03-03-1200",
  "generated_at": "2026-03-03T12:00:00",
  "size": 536371,
  "cities": ["Taoyuan"],
  "stats": {
    "total_cities": 1,
    "total_routes": 50,
    "total_stops": 1234
  },
  "available": true
}

# Download bundle
curl http://localhost:8000/bus/api/bundle/download -o bundle.json.gz

# Get single city
curl http://localhost:8000/bus/api/bundle/city/Taoyuan
```

---

## Frontend Integration

### 1. Create Bundle Manager Composable

```typescript
// src/composables/useBusBundle.ts
import { ref, computed } from 'vue';

interface BundleVersion {
  version: string;
  generated_at: string;
  size: number;
  cities: string[];
  available: boolean;
}

interface BundleData {
  version: string;
  cities: Record<string, any>;
}

const BUNDLE_STORAGE_KEY = 'bus_bundle_data';
const BUNDLE_VERSION_KEY = 'bus_bundle_version';

export function useBusBundle() {
  const loading = ref(false);
  const error = ref<string | null>(null);
  const bundleData = ref<BundleData | null>(null);

  // Load bundle from localStorage
  function loadFromStorage(): BundleData | null {
    try {
      const stored = localStorage.getItem(BUNDLE_STORAGE_KEY);
      if (stored) {
        return JSON.parse(stored);
      }
    } catch (e) {
      console.error('Failed to load bundle from storage:', e);
    }
    return null;
  }

  // Save bundle to localStorage
  function saveToStorage(data: BundleData) {
    try {
      localStorage.setItem(BUNDLE_STORAGE_KEY, JSON.stringify(data));
      localStorage.setItem(BUNDLE_VERSION_KEY, data.version);
    } catch (e) {
      console.error('Failed to save bundle to storage:', e);
    }
  }

  // Get current local version
  function getLocalVersion(): string | null {
    return localStorage.getItem(BUNDLE_VERSION_KEY);
  }

  // Check for updates
  async function checkForUpdates(): Promise<boolean> {
    try {
      const response = await fetch('/bus/api/bundle/version');
      const serverVersion: BundleVersion = await response.json();

      if (!serverVersion.available) {
        console.warn('Bundle not available on server');
        return false;
      }

      const localVersion = getLocalVersion();

      // Need update if no local version or different version
      return !localVersion || localVersion !== serverVersion.version;

    } catch (e) {
      console.error('Failed to check bundle version:', e);
      return false;
    }
  }

  // Download and install bundle
  async function downloadBundle() {
    loading.value = true;
    error.value = null;

    try {
      const response = await fetch('/bus/api/bundle/download');

      if (!response.ok) {
        throw new Error(`Download failed: ${response.status}`);
      }

      // Decompress and parse
      const blob = await response.blob();
      const decompressed = await decompressGzip(blob);
      const data: BundleData = JSON.parse(decompressed);

      // Save to storage
      saveToStorage(data);
      bundleData.value = data;

      console.log(`Bundle v${data.version} downloaded and installed`);
      return true;

    } catch (e) {
      error.value = `Failed to download bundle: ${e}`;
      console.error(error.value);
      return false;
    } finally {
      loading.value = false;
    }
  }

  // Initialize: check and download if needed
  async function initialize() {
    // Load from storage first
    bundleData.value = loadFromStorage();

    // Check for updates
    const needsUpdate = await checkForUpdates();

    if (needsUpdate) {
      console.log('Bundle update available, downloading...');
      await downloadBundle();
    } else {
      console.log('Bundle is up to date');
    }
  }

  // Get route data from bundle
  function getRouteData(city: string, routeId: string) {
    if (!bundleData.value) return null;
    return bundleData.value.cities[city]?.routes[routeId] || null;
  }

  // Get all routes for a city
  function getCityRoutes(city: string) {
    if (!bundleData.value) return [];
    const routes = bundleData.value.cities[city]?.routes || {};
    return Object.entries(routes).map(([id, data]) => ({
      id,
      ...data
    }));
  }

  return {
    loading,
    error,
    bundleData,
    initialize,
    checkForUpdates,
    downloadBundle,
    getRouteData,
    getCityRoutes,
  };
}

// Helper: Decompress gzip blob
async function decompressGzip(blob: Blob): Promise<string> {
  const ds = new DecompressionStream('gzip');
  const stream = blob.stream().pipeThrough(ds);
  const decompressedBlob = await new Response(stream).blob();
  return await decompressedBlob.text();
}
```

### 2. Initialize on App Load

```typescript
// src/boot/bus-bundle.ts
import { boot } from 'quasar/wrappers';
import { useBusBundle } from 'src/composables/useBusBundle';

export default boot(async ({ app }) => {
  const busBundle = useBusBundle();

  // Initialize bundle on app start
  await busBundle.initialize();

  // Provide globally
  app.provide('busBundle', busBundle);
});
```

### 3. Use in Components

```vue
<script setup lang="ts">
import { ref, onMounted, inject } from 'vue';
import { useBusBundle } from '@/composables/useBusBundle';

const routeId = ref('709');
const city = ref('Taoyuan');

const busBundle = inject('busBundle') || useBusBundle();

const routeData = computed(() => {
  return busBundle.getRouteData(city.value, routeId.value);
});

const stops = computed(() => {
  return routeData.value?.stops['0'] || [];
});

onMounted(async () => {
  // Ensure bundle is loaded
  if (!busBundle.bundleData.value) {
    await busBundle.initialize();
  }
});
</script>

<template>
  <div>
    <h3>Route {{ routeId }}</h3>
    <div v-if="routeData">
      <p>From: {{ routeData.from }}</p>
      <p>To: {{ routeData.to }}</p>

      <h4>Stops</h4>
      <ul>
        <li v-for="stop in stops" :key="stop.id">
          {{ stop.name }} ({{ stop.lat }}, {{ stop.lng }})
        </li>
      </ul>
    </div>
    <div v-else>
      Loading route data...
    </div>
  </div>
</template>
```

---

## Performance Metrics

### Before OTA (Without Bundle)

**Scenario**: User views 5 routes, each with 30 stops

| API Call | Count | Size | Total |
|----------|-------|------|-------|
| GET ?stop&709 | 5 | 15KB | 75KB |
| GET ?mapstop&709 | 5 | 12KB | 60KB |
| GET ?mapshape&709 | 5 | 8KB | 40KB |
| **Total** | **15** | - | **175KB** |

**API Requests**: 15 requests for static data

---

### After OTA (With Bundle)

**Scenario**: User views 5 routes, each with 30 stops

| API Call | Count | Size | Total |
|----------|-------|------|-------|
| GET /bundle/version | 1 | 0.5KB | 0.5KB |
| GET /bundle/download | 1 (weekly) | 500KB | 500KB |
| **Static lookups** | - | localStorage | 0 API calls |

**API Requests**: 1 request (version check), 1 download per week

**Savings**: 93% fewer API calls!

---

## Configuration

### Environment Variables

```bash
# .env
BUS_BUNDLE_PATH=static/bus/bundle.json.gz
BUS_BUNDLE_MAX_ROUTES_PER_CITY=50   # Limit routes per city
```

### Bundle Size Limits

| Cities | Routes | Uncompressed | Compressed |
|--------|--------|--------------|------------|
| 1 (Taoyuan) | 50 | ~2.5MB | ~500KB |
| 3 (Major) | 150 | ~7MB | ~1.5MB |
| All (22) | 3000+ | ~50MB | ~10MB |

**Recommendation**: Start with 1-3 major cities, expand as needed.

---

## Troubleshooting

### Bundle Generation Fails

```bash
# Check TDX credentials
echo $TDX_CLIENT_ID
echo $TDX_CLIENT_SECRET

# Test TDX connection
python3 -c "from tdx_client import TDXClient; c = TDXClient(); print(c.get_routes('Taoyuan')[:1])"

# Check permissions
ls -la static/bus/

# Manually create directory
mkdir -p static/bus/
```

### Bundle Not Updating

```bash
# Check cron job
crontab -l | grep bundle

# Check logs
tail -f logs/bus_bundle.log

# Manually trigger
python3 scripts/generate_bus_bundle.py --city Taoyuan
```

### Frontend Not Downloading

```javascript
// Check version endpoint
fetch('/bus/api/bundle/version')
  .then(r => r.json())
  .then(console.log);

// Clear localStorage and retry
localStorage.removeItem('bus_bundle_data');
localStorage.removeItem('bus_bundle_version');
```

---

## Best Practices

### 1. Incremental Rollout
```javascript
// Start with single city
await busBundle.downloadCityBundle('Taoyuan');

// Expand gradually
if (user.location === 'Taipei') {
  await busBundle.downloadCityBundle('Taipei');
}
```

### 2. Background Updates
```javascript
// Don't block UI
setTimeout(async () => {
  const needsUpdate = await busBundle.checkForUpdates();
  if (needsUpdate) {
    await busBundle.downloadBundle();
  }
}, 5000); // Check after 5 seconds
```

### 3. Quota Management
```javascript
// Only download on WiFi
if (navigator.connection?.type === 'wifi') {
  await busBundle.downloadBundle();
}
```

---

## Monitoring

### Bundle Stats Endpoint

```bash
curl http://localhost:8000/bus/api/bundle/version

# Response includes stats:
{
  "stats": {
    "total_cities": 1,
    "total_routes": 50,
    "total_stops": 1234
  }
}
```

### Log Analysis

```bash
# View generation logs
tail -100 logs/bus_bundle.log

# Count successful generations
grep "Bundle generated" logs/bus_bundle.log | wc -l

# Check for errors
grep "ERROR" logs/bus_bundle.log
```

---

## Roadmap

- [ ] **Differential updates**: Only download changed routes
- [ ] **City-specific downloads**: Per-city bundles
- [ ] **IndexedDB storage**: For larger datasets
- [ ] **Service Worker caching**: True offline support
- [ ] **CDN integration**: Serve from CDN instead of API server

---

## Related Files

- `scripts/generate_bus_bundle.py` - Bundle generator
- `scripts/setup_bundle_cron.sh` - Cron job setup
- `bus_api.py` - Bundle serving endpoints
- `docs/BUS_API_DESIGN.md` - Overall architecture
