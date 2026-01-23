# Admin Panel Feature

## Overview

Added a comprehensive admin panel to the ConfigCard component with authentication, statistics display, and management controls for midnight sync, cache, and background jobs.

## Features

### 1. Admin Login
- **Location**: ConfigCard settings dialog
- **Credentials**: `admin` / `admin` (hardcoded for now, should be secured in production)
- **Access**: Click "Admin" button after entering credentials

### 2. Statistics Display

#### Cache Stats
- Books in database
- Chapters in database
- Memory cache size

#### Job Stats
- Pending jobs
- Completed jobs
- Failed jobs

#### Midnight Sync Stats
- Total books in queue
- Status breakdown: Pending, Syncing, Completed, Failed
- Next scheduled sync time

### 3. Management Actions

#### Midnight Sync Actions
1. **Enqueue** - Add all unfinished books to sync queue
   - Endpoint: `POST /admin/midnight-sync/enqueue-unfinished`
   - Returns count of books added

2. **Trigger** - Manually start midnight sync immediately
   - Endpoint: `POST /admin/midnight-sync/trigger`
   - Runs sync in background thread

3. **Clear** - Remove completed/failed entries from queue
   - Endpoint: `POST /admin/midnight-sync/clear-completed`
   - Returns count of entries removed

4. **Refresh** - Reload all statistics
   - Fetches latest data from `/health` and `/admin/midnight-sync/stats`

#### Cache Management
1. **Clear Memory Cache** - Clear in-memory cache (DB remains intact)
   - Endpoint: `POST /admin/cache/clear`
   - Shows confirmation dialog before clearing

## Implementation Details

### Frontend ([src/components/ConfigCard.vue](src/components/ConfigCard.vue))

**New State Variables:**
```typescript
const isAdminLoggedIn = ref(false);
const adminUsername = ref('');
const adminPassword = ref('');
const adminLoading = ref(false);
const statsLoading = ref(false);
const actionLoading = ref({
  enqueue: false,
  trigger: false,
  clear: false,
  clearCache: false
});

const stats = ref<{
  cache: CacheStats | null;
  jobs: JobStats | null;
  midnightSync: MidnightSyncStats | null;
}>({
  cache: null,
  jobs: null,
  midnightSync: null
});
```

**Key Functions:**
- `adminLogin()` - Validates credentials and shows admin panel
- `adminLogout()` - Clears session and hides admin panel
- `refreshStats()` - Fetches latest stats from backend
- `enqueueUnfinished()` - Enqueue all unfinished books
- `triggerSync()` - Trigger midnight sync manually
- `clearCompleted()` - Clear completed/failed sync entries
- `clearCache()` - Clear in-memory cache with confirmation

**Auto-refresh:**
- Stats automatically refresh when admin panel is shown
- Each action triggers a stats refresh on completion

### Backend ([main_optimized.py](main_optimized.py))

**Existing Admin Endpoints:**
- `GET /admin/jobs/stats` - Get background job statistics
- `POST /admin/jobs/sync/{book_id}` - Manually sync a specific book
- `POST /admin/jobs/clear_history` - Clear job history
- `POST /admin/cache/clear` - Clear in-memory cache
- `POST /admin/cache/invalidate/{book_id}` - Invalidate cache for a book
- `GET /admin/stats` - Get detailed cache statistics
- `GET /admin/midnight-sync/stats` - Get midnight sync queue stats
- `POST /admin/midnight-sync/clear-completed` - Clear completed/failed entries
- `POST /admin/midnight-sync/trigger` - Manually trigger midnight sync
- `POST /admin/midnight-sync/enqueue-unfinished` - Enqueue unfinished books

**Key Backend Fix:**
Updated response field from `count` to `removed_count` in `/admin/midnight-sync/clear-completed` to match frontend expectations.

## UI/UX

### Visual Design
- Admin panel has subtle blue background (rgba(33, 150, 243, 0.05))
- Fade-in animation when panel opens
- Color-coded buttons:
  - **Primary (blue)** - Enqueue
  - **Secondary (purple)** - Trigger
  - **Warning (orange)** - Clear
  - **Info (cyan)** - Refresh
  - **Negative (red)** - Clear Cache

### Stats Cards
- Compact card layout with spinners during loading
- Real-time data display
- Responsive grid layout (2 columns for cache/jobs, full width for midnight sync)

### Action Buttons
- Loading states for all actions
- Tooltips explaining each action
- Confirmation dialog for destructive actions (clear cache)
- Success/error notifications using Quasar Notify

## Usage

### For Users
1. Open Settings (gear icon in header)
2. Scroll to bottom of settings dialog
3. Enter admin credentials: `admin` / `admin`
4. Click "Admin" button
5. View stats and use management buttons

### For Developers

**Testing Locally:**
```bash
# Build and run
docker compose -f compose.yml -f docker/build.yml build xsw
docker compose up -d xsw

# Access at http://localhost:8000/xsw/spa/
```

**Test Admin Endpoints:**
```bash
# Get health stats
curl http://localhost:8000/xsw/api/health

# Get midnight sync stats
curl http://localhost:8000/xsw/api/admin/midnight-sync/stats

# Enqueue unfinished books
curl -X POST http://localhost:8000/xsw/api/admin/midnight-sync/enqueue-unfinished

# Trigger sync
curl -X POST http://localhost:8000/xsw/api/admin/midnight-sync/trigger

# Clear completed
curl -X POST http://localhost:8000/xsw/api/admin/midnight-sync/clear-completed

# Clear cache
curl -X POST http://localhost:8000/xsw/api/admin/cache/clear
```

## Security Considerations

### Current Implementation (Development)
- **Hardcoded credentials**: `admin` / `admin`
- **Client-side validation only**
- **No session management**
- **No HTTPS enforcement**

### Production Recommendations
1. **Backend Authentication**
   - Add proper authentication endpoints
   - Use JWT or session tokens
   - Store credentials securely (hashed passwords)

2. **HTTPS Only**
   - Require HTTPS for admin endpoints
   - Add CORS restrictions

3. **Rate Limiting**
   - Limit login attempts
   - Add API rate limiting

4. **Audit Logging**
   - Log all admin actions
   - Track who performed what action

5. **Role-Based Access**
   - Different permission levels
   - Separate read-only vs full admin

## Styling

**Custom CSS Classes:**
```css
.admin-panel {
  animation: fadeIn 0.4s ease-in;
  padding: 8px;
  border-radius: 8px;
  background: rgba(33, 150, 243, 0.05);
}

.q-dark .admin-panel {
  background: rgba(33, 150, 243, 0.1);
}
```

**Dark Mode Support:**
- Automatically adjusts background opacity in dark mode
- All Quasar components support dark mode natively

## Future Enhancements

1. **Real-time Updates**
   - WebSocket connection for live stats
   - Auto-refresh stats every 30 seconds

2. **Charts and Graphs**
   - Visual representation of sync progress
   - Historical data trends

3. **Job Management**
   - View individual job details
   - Cancel running jobs
   - Retry failed jobs

4. **Advanced Filtering**
   - Filter books by status
   - Search in sync queue
   - Sort by priority/date

5. **Bulk Operations**
   - Select multiple books
   - Batch enqueue/remove
   - Export queue data

## Files Modified

1. **Frontend**
   - [src/components/ConfigCard.vue](src/components/ConfigCard.vue) - Added admin panel UI and logic

2. **Backend**
   - [main_optimized.py](main_optimized.py:963) - Fixed response field name

## Testing Checklist

- [x] Admin login works with correct credentials
- [x] Admin login rejects incorrect credentials
- [x] Stats display correctly after login
- [x] Enqueue button adds unfinished books
- [x] Trigger button starts midnight sync
- [x] Clear button removes completed entries
- [x] Refresh button updates stats
- [x] Clear cache shows confirmation dialog
- [x] Clear cache removes memory cache entries
- [x] Logout button clears session
- [x] Auto-refresh works on login
- [x] Loading states show correctly
- [x] Error notifications display on failure
- [x] Success notifications display on success

## Known Issues

None currently.

---

**Created:** 2026-01-22
**Author:** AI Assistant
**Status:** ✅ Complete and tested
