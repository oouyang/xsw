# Bus API Usage Guide

## Quick Start

### 1. Register TDX Account
Visit https://tdx.transportdata.tw/ and create an account to get your API credentials.

### 2. Configure Environment
Add your TDX credentials to `.env`:
```bash
TDX_CLIENT_ID=your_client_id
TDX_CLIENT_SECRET=your_client_secret
BUS_DEFAULT_CITY=Taoyuan
```

### 3. Test the API
```bash
# Start server
uvicorn main_optimized:app --reload --port 8000

# Test arrival times for route 709
curl "http://localhost:8000/bus/api?estime&709"

# Test bus positions
curl "http://localhost:8000/bus/api?plate&709"
```

---

## API Endpoints

### 1. Estimated Arrival Times
**Endpoint**: `GET /bus/api?estime&{route_id}`

**Example**:
```bash
curl "http://localhost:8000/bus/api?estime&709"
```

**Response** (pipe-separated):
```
709,200,OK,1
0_TAO6116_16:37_|0_TAO6120_120_KKA-1265|0_TAO6130_0_KKB-0281|1_TAO9566_720_KKA-1262
```

**Format**: `direction_stopId_time_plate`
- `direction`: 0 (outbound) or 1 (return)
- `stopId`: Stop unique identifier
- `time`: Seconds until arrival (or HH:MM for schedule)
- `plate`: Bus plate number (empty if none)

---

### 2. Bus Plates & Positions
**Endpoint**: `GET /bus/api?plate&{route_id}`

**Example**:
```bash
curl "http://localhost:8000/bus/api?plate&709"
```

**Response**:
```
709,200,OK
0_TAO6150_KKA-1252_0_0|1_TAO6149_KKA-1258_1_0|0_TAO6130_KKB-0281_1_0
```

**Format**: `direction_stopId_plate_atStopFlag_0`
- `atStopFlag`: 1 if bus is at stop, 0 otherwise

---

### 3. Stop List
**Endpoint**: `GET /bus/api?stop&{route_id}`

**Example**:
```bash
curl "http://localhost:8000/bus/api?stop&709"
```

**Response** (JSON):
```json
{
  "routeId": "709",
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

### 4. Stop Coordinates (for Map)
**Endpoint**: `GET /bus/api?mapstop&{route_id}`

**Example**:
```bash
curl "http://localhost:8000/bus/api?mapstop&709"
```

**Response** (JSON):
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

### 5. Route Shape (for Map)
**Endpoint**: `GET /bus/api?mapshape&{route_id}`

**Example**:
```bash
curl "http://localhost:8000/bus/api?mapshape&709"
```

**Response** (JSON):
```json
{
  "routeId": "709",
  "shapes": {
    "0": [[121.2168, 24.9515], [121.2175, 24.9523]],
    "1": [[121.2180, 24.9530], [121.2185, 24.9535]]
  }
}
```

---

### 6. Real-time Bus Positions
**Endpoint**: `GET /bus/api?mapbus&{route_id}`

**Example**:
```bash
curl "http://localhost:8000/bus/api?mapbus&709"
```

**Response** (JSON):
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
      "updateTime": "2026-03-03T10:30:15+08:00"
    }
  ]
}
```

---

### 7. Route List
**Endpoint**: `GET /bus/api?route&{city}`

**Example**:
```bash
curl "http://localhost:8000/bus/api?route&Taoyuan"
```

**Response** (JSON):
```json
{
  "city": "Taoyuan",
  "routes": [
    {"id": "709", "name": "709", "from": "平鎮分局", "to": "永寧轉運站"},
    {"id": "710", "name": "710", "from": "...", "to": "..."}
  ]
}
```

---

## Frontend Integration Example

### Vue Composable
```javascript
// src/composables/useBusApi.ts
import { ref } from 'vue';

export function useBusApi() {
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function getArrivalTimes(routeId: string) {
    loading.value = true;
    error.value = null;

    try {
      const response = await fetch(`/bus/api?estime&${routeId}`);
      const text = await response.text();

      // Parse pipe-separated response
      const lines = text.split('\n');
      const header = lines[0].split(',');
      const data = lines[1];

      if (header[1] !== '200') {
        throw new Error('API error');
      }

      const arrivals = data.split('|').map(record => {
        const [dir, stopId, time, plate] = record.split('_');
        return {
          direction: parseInt(dir),
          stopId,
          estimateTime: time,
          plateNumber: plate
        };
      });

      return arrivals;
    } catch (e) {
      error.value = e.message;
      return [];
    } finally {
      loading.value = false;
    }
  }

  async function getBusPositions(routeId: string) {
    const response = await fetch(`/bus/api?mapbus&${routeId}`);
    return response.json();
  }

  return {
    loading,
    error,
    getArrivalTimes,
    getBusPositions
  };
}
```

### Component Usage
```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useBusApi } from '@/composables/useBusApi';

const routeId = ref('709');
const arrivals = ref([]);
const busApi = useBusApi();

onMounted(async () => {
  arrivals.value = await busApi.getArrivalTimes(routeId.value);

  // Poll every 10 seconds
  setInterval(async () => {
    arrivals.value = await busApi.getArrivalTimes(routeId.value);
  }, 10000);
});
</script>

<template>
  <div>
    <h3>Route {{ routeId }} Arrivals</h3>
    <div v-for="arrival in arrivals" :key="arrival.stopId">
      <div>{{ arrival.stopId }}: {{ arrival.estimateTime }}s</div>
      <div v-if="arrival.plateNumber">Bus: {{ arrival.plateNumber }}</div>
    </div>
  </div>
</template>
```

---

## Performance Tips

### Caching Strategy
- **Real-time data** (estime, plate, mapbus): 30s cache
- **Static data** (stop, mapstop, mapshape): 24h cache
- **Route list**: 24h cache

### Polling Recommendations
```javascript
// Good: 10-15 second intervals
setInterval(fetchArrivals, 10000);

// Bad: Too frequent (wastes API quota)
setInterval(fetchArrivals, 1000);
```

### Rate Limiting
- Backend enforces 60 requests/minute per IP
- Frontend should implement per-route polling (not all routes at once)

---

## TDX API Limits

| Tier | Requests/Day | Requests/Minute |
|------|--------------|-----------------|
| Free | 2,000 | 20 |
| Basic | 20,000 | 100 |
| Premium | 200,000 | 500 |

**Recommendation**: Use basic tier for production, implement aggressive caching.

---

## Troubleshooting

### 1. "401 Unauthorized"
- Check TDX_CLIENT_ID and TDX_CLIENT_SECRET in .env
- Verify credentials at https://tdx.transportdata.tw/

### 2. "500 Internal Server Error"
- Check server logs: `docker logs xsw --tail 100`
- Verify TDX API is accessible
- Check SSL/proxy settings (VERIFY_SSL=false if behind corporate proxy)

### 3. Empty Response
- Route ID might not exist in that city
- Try different city: `BUS_DEFAULT_CITY=Taipei`
- Check TDX API limits (quota exceeded)

### 4. Slow Response
- Check TDX API status
- Verify cache is working (check logs for cache hits)
- Consider increasing cache TTL

---

## Next Steps

1. **Implement Static Bundle**: Generate weekly bundle with all routes/stops
2. **Add Frontend UI**: Build Vue components for bus tracking
3. **Map Integration**: Add Leaflet/Mapbox for real-time visualization
4. **Push Notifications**: Alert users when bus is arriving
5. **Offline Support**: Cache static data in Service Worker

---

## Related Files

- `tdx_client.py` - TDX API client with OAuth2
- `bus_transformer.py` - Data transformation (TDX → yunbus)
- `bus_cache.py` - In-memory TTL cache
- `bus_api.py` - FastAPI endpoints
- `docs/BUS_API_DESIGN.md` - Complete architecture design
