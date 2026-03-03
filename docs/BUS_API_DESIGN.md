# Bus API Design - TDX Integration

## Overview
Build a yunbus-style bus API using TDX as the data source, integrated into the XSW project.

## Architecture

```
┌─────────────┐
│  Frontend   │
│  (Vue 3)    │
└──────┬──────┘
       │
       ├─── Static Bundle (weekly download)
       │    • Routes, Stops, Shapes
       │    • ~2MB compressed JSON
       │
       └─── Real-time API (FastAPI)
            • Arrival times, bus positions
            • Pipe-separated format (yunbus-style)
```

## API Endpoints

### 1. `GET /bus/api?estime&{route_id}`
**Description**: Estimated arrival times (yunbus format)

**Response Format** (pipe-separated):
```
ROUTE_ID,200,OK,1
direction_stopId_estimateTime_plate|direction_stopId_estimateTime_plate...

Example:
709,200,OK,1
0_TAO6116_16:37_|0_TAO6120_120_KKA-1265|0_TAO6130_0_KKB-0281|1_TAO9566_720_KKA-1262
```

**Mapping from TDX**:
- `direction` → TDX `Direction` (0 or 1)
- `stopId` → TDX `StopUID`
- `estimateTime` → TDX `EstimateTime` (seconds) or "HH:MM" for scheduled
- `plate` → TDX `PlateNumb` (empty if no bus)

---

### 2. `GET /bus/api?plate&{route_id}`
**Description**: Bus plate numbers and positions

**Response Format**:
```
ROUTE_ID,200,OK
direction_stopId_plate_atStopFlag_|...

Example:
709,200,OK
0_TAO6150_KKA-1252_0_0|1_TAO6149_KKA-1258_1_0|0_TAO6130_KKB-0281_1_0
```

**Mapping from TDX**:
- Match `PlateNumb` with stops via `EstimatedTimeOfArrival` + `RealTimeByFrequency`
- `atStopFlag` = 1 if `EstimateTime == 0`, else 0

---

### 3. `GET /bus/api?stop&{route_id}`
**Description**: Stop list (from static bundle)

**Response Format** (JSON):
```json
{
  "routeId": "709",
  "routeName": "709",
  "stops": {
    "0": [
      {"id": "TAO6116", "name": "平鎮分局", "seq": 1},
      {"id": "TAO6120", "name": "平南國中", "seq": 2}
    ],
    "1": [...]
  }
}
```

---

### 4. `GET /bus/api?mapstop&{route_id}`
**Description**: Stop coordinates for map

**Response Format** (JSON):
```json
{
  "routeId": "709",
  "stops": [
    {"id": "TAO6116", "lat": 24.9515, "lng": 121.2168, "dir": 0},
    {"id": "TAO6120", "lat": 24.9523, "lng": 121.2175, "dir": 0}
  ]
}
```

---

### 5. `GET /bus/api?mapshape&{route_id}`
**Description**: Route path for map

**Response Format** (JSON):
```json
{
  "routeId": "709",
  "shapes": {
    "0": [[121.2168, 24.9515], [121.2175, 24.9523], ...],
    "1": [...]
  }
}
```

---

### 6. `GET /bus/api?mapbus&{route_id}`
**Description**: Real-time bus positions

**Response Format** (JSON):
```json
{
  "routeId": "709",
  "buses": [
    {
      "plate": "KKA-1252",
      "dir": 0,
      "lat": 24.9520,
      "lng": 121.2170,
      "speed": 45,
      "azimuth": 90,
      "updateTime": "2026-03-03T10:30:15"
    }
  ]
}
```

---

### 7. `GET /bus/api?route&{city}`
**Description**: List all routes in a city

**Response Format** (JSON):
```json
{
  "city": "Taoyuan",
  "routes": [
    {"id": "709", "name": "709", "from": "起點", "to": "終點"},
    {"id": "710", "name": "710", "from": "...", "to": "..."}
  ]
}
```

---

## Static Bundle Design

### Bundle Structure
```json
{
  "version": "2026-03-03",
  "cities": {
    "Taoyuan": {
      "routes": {
        "709": {
          "name": "709",
          "from": "平鎮分局",
          "to": "永寧轉運站",
          "stops": {
            "0": [
              {"id": "TAO6116", "name": "平鎮分局", "lat": 24.9515, "lng": 121.2168, "seq": 1},
              {"id": "TAO6120", "name": "平南國中", "lat": 24.9523, "lng": 121.2175, "seq": 2}
            ],
            "1": [...]
          },
          "shapes": {
            "0": [[121.2168, 24.9515], [121.2175, 24.9523], ...],
            "1": [...]
          }
        }
      }
    }
  }
}
```

### Bundle Generation
- **Frequency**: Weekly (via cron job)
- **Size**: ~2-5MB compressed (gzip)
- **Endpoint**: `GET /bus/static/bundle.json.gz`
- **Caching**: CDN-friendly with ETag

### Bundle Usage
```javascript
// Frontend
const bundle = await fetch('/bus/static/bundle.json.gz')
  .then(r => r.json());

localStorage.setItem('bus_bundle', JSON.stringify(bundle));
localStorage.setItem('bus_bundle_version', bundle.version);
```

---

## Implementation Plan

### Phase 1: Backend Foundation
1. Create TDX API client with OAuth2 authentication
2. Implement cache layer (Redis/SQLite)
3. Create transformation layer (TDX → yunbus format)

### Phase 2: API Endpoints
1. Implement `?estime` endpoint
2. Implement `?plate` endpoint
3. Implement `?mapbus` endpoint
4. Implement static endpoints (`?stop`, `?mapstop`, `?mapshape`, `?route`)

### Phase 3: Static Bundle
1. Create bundle generator script
2. Set up weekly cron job
3. Implement compression & CDN serving

### Phase 4: Frontend Integration
1. Create Vue composable for bus data
2. Implement bundle loading with version check
3. Build real-time API polling
4. Create UI components (map, arrival list)

---

## Performance Optimizations

### Backend
1. **Cache Strategy**:
   - Static data (routes, stops, shapes): 24h TTL
   - Real-time data (arrivals, positions): 30s TTL
   - Use Redis for distributed caching

2. **Response Compression**:
   - gzip for JSON responses
   - Pipe-separated format for real-time data (50% smaller than JSON)

3. **Rate Limiting**:
   - Per-IP: 60 requests/minute
   - Per-route: 1 request/10s (prevent spam)

### Frontend
1. **Bundle Strategy**:
   - Check version on app load
   - Download only if outdated
   - Store in localStorage (fallback to IndexedDB)

2. **Polling Strategy**:
   - Arrival times: 10s interval
   - Bus positions: 15s interval
   - Only poll active route

3. **UI Optimizations**:
   - Virtual scrolling for long stop lists
   - Map clustering for multiple buses
   - Lazy load route shapes

---

## File Structure

```
/opt/ws/xsw/
├── tdx_client.py              # TDX API client
├── bus_api.py                 # Bus endpoints
├── bus_cache.py               # Cache manager
├── bus_transformer.py         # TDX → yunbus format
├── scripts/
│   └── generate_bus_bundle.py # Static bundle generator
└── static/
    └── bus/
        └── bundle.json.gz     # Static bundle
```

---

## Environment Variables

```bash
# .env
TDX_CLIENT_ID=your_client_id
TDX_CLIENT_SECRET=your_client_secret
TDX_BASE_URL=https://tdx.transportdata.tw/api/basic
TDX_AUTH_URL=https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token
BUS_CACHE_TTL_STATIC=86400      # 24 hours
BUS_CACHE_TTL_REALTIME=30       # 30 seconds
BUS_BUNDLE_PATH=/opt/ws/xsw/static/bus/bundle.json.gz
```

---

## Next Steps

1. **Register TDX Account**: Get app ID and app key
2. **Implement TDX Client**: OAuth2 + API wrapper
3. **Build Transformer**: Map TDX → yunbus format
4. **Create Endpoints**: FastAPI routes
5. **Generate Bundle**: Static data package
6. **Frontend Integration**: Vue components + API client
