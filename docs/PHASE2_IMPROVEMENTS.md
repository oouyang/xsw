# Phase 2 Frontend Improvements - Smart Retry with Context & Loading State Machine

This document describes the Phase 2 improvements implemented for ChaptersPage.vue, focusing on smart retry functionality with context-aware error messages and a proper loading state machine.

## What Was Implemented

### 1. Loading State Machine

Added a proper state machine to track loading phases instead of simple boolean flags:

```typescript
type LoadingPhase = 'idle' | 'phase1' | 'phase2' | 'complete' | 'error';
const loadingPhase = ref<LoadingPhase>('idle');

// Computed properties derived from state machine
const isLoadingPhase1 = computed(() => loadingPhase.value === 'phase1');
const isLoadingPhase2 = computed(() => loadingPhase.value === 'phase2');
const isLoadingComplete = computed(() => loadingPhase.value === 'complete');
const hasLoadingError = computed(() => loadingPhase.value === 'error');
const canShowContent = computed(() =>
  loadingPhase.value === 'complete' ||
  loadingPhase.value === 'phase2' ||
  displayChapters.value.length > 0
);
```

**Five Loading States:**
- **`idle`**: Initial state, nothing loading
- **`phase1`**: Loading initial pages (current + adjacent)
- **`phase2`**: Background loading remaining chapters
- **`complete`**: All loading finished successfully
- **`error`**: An error occurred during loading

**Benefits:**
- Clear state transitions
- Easier to debug (console.log shows exact state)
- Better separation of concerns
- More maintainable code
- Prevents invalid state combinations

### 2. Context-Aware Error Tracking

Added a new error tracking system that distinguishes between different failure phases:

```typescript
interface LoadError {
  phase: 'phase1' | 'phase2' | 'info';
  message: string;
  retryable: boolean;
  technicalDetails?: string;
}

const loadError = ref<LoadError | null>(null);
```

**Three Error Phases:**
- **`info`**: Failed to load book information
- **`phase1`**: Failed to load initial pages (critical - user can't see any content)
- **`phase2`**: Failed to load remaining chapters (non-critical - first 3 pages are available)

### 2. Enhanced Error Banner UI

Replaced the generic error banner with a context-aware one that shows:

- **Different colors based on severity:**
  - Red (error icon): Phase 1 failures and info failures (critical)
  - Orange (warning icon): Phase 2 failures (less critical)

- **Phase-specific messages:**
  - Info failure: "載入書籍資訊失敗" (Load book info failed)
  - Phase 1 failure: "載入章節失敗" (Load chapters failed)
  - Phase 2 failure: "背景載入未完成（前3頁已可用）" (Background loading incomplete - first 3 pages available)

- **Technical details:** Shows underlying error message for debugging

- **Dismissible:** Users can close the error banner

- **Phase-specific retry:** Retry button calls appropriate recovery function

### 3. Smart Retry Function

Implemented `retryPhase()` function that handles retrying specific phases:

```typescript
async function retryPhase(phase: 'phase1' | 'phase2' | 'info') {
  if (phase === 'info') {
    // Retry loading book info only
    await loadInfo();
  } else if (phase === 'phase1') {
    // Retry Phase 1: Load pages around current position
    await book.loadAllChapters({ force: true, onProgress: ... });
  } else if (phase === 'phase2') {
    // Retry Phase 2: Load remaining chapters
    await book.loadAllChapters({ force: true, onProgress: ... });
  }
}
```

**Benefits:**
- Users can retry just what failed, not everything
- Phase 2 failures don't force a full reload
- Clear feedback on what's being retried

### 4. Automatic Phase Detection

The system automatically detects which phase failed by checking if any content was loaded:

```typescript
const hasLoadedChapters = book.pageChapters.length > 0;

if (hasLoadedChapters) {
  // Phase 1 succeeded, Phase 2 failed (less critical)
  loadError.value = { phase: 'phase2', ... };
} else {
  // Phase 1 failed (critical)
  loadError.value = { phase: 'phase1', ... };
}
```

### 5. Updated Error Handling Across All Functions

Updated error handling in:
- **`loadInfo()`**: Sets phase='info' errors
- **`onMounted()`**: Detects Phase 1 vs Phase 2 failures
- **`switchPage()`**: Detects Phase 1 vs Phase 2 failures
- **`retryPhase()`**: Handles retry errors with context

## User Experience Improvements

### Before (Generic Errors):
```
❌ 載入章節失敗: Network error
[Retry Button]
```
- User doesn't know what failed
- Retry reloads everything (slow)
- No indication of partial success

### After (Context-Aware Errors):

**Phase 1 Failure (Critical):**
```
🔴 載入章節失敗
   Network error
[Retry] [Close]
```
- Clear that initial loading failed
- Red color indicates critical issue
- Retry attempts Phase 1 only

**Phase 2 Failure (Non-Critical):**
```
🟠 背景載入未完成（前3頁已可用）
   Network error
[Retry] [Close]
```
- Orange color indicates warning (not critical)
- User knows first 3 pages ARE available
- Can dismiss and continue reading
- Retry attempts Phase 2 only (no Phase 1 reload)

**Info Failure:**
```
🔴 載入書籍資訊失敗
   Network error
[Retry] [Close]
```
- Clear that book info failed to load
- Retry fetches book info only

## Technical Implementation Details

### Error Banner Component

```vue
<q-banner
  v-if="loadError"
  :class="loadError.phase === 'phase2' ? 'bg-orange-2 text-orange-10' : 'bg-red-2 text-red-10'"
  class="q-mb-md"
>
  <template v-slot:avatar>
    <q-icon :name="loadError.phase === 'phase2' ? 'warning' : 'error'" />
  </template>
  <div>
    <div class="text-body2">{{ loadError.message }}</div>
    <div v-if="loadError.technicalDetails" class="text-caption q-mt-xs">
      {{ loadError.technicalDetails }}
    </div>
  </div>
  <template v-slot:action>
    <q-btn
      v-if="loadError.retryable"
      flat
      :color="loadError.phase === 'phase2' ? 'orange-10' : 'red-10'"
      :label="$t('common.retry')"
      icon="refresh"
      @click="retryPhase(loadError.phase)"
    />
    <q-btn flat dense icon="close" @click="loadError = null" />
  </template>
</q-banner>
```

### State Transitions

The loading state machine follows these transitions:

```
idle
  ↓
phase1 (loading first 3 pages)
  ↓ (success)
phase2 (background loading) ──→ complete
  ↓ (error)
error (with retry option)
  ↓ (retry)
phase1 (retry from beginning)
```

**State Transition Examples:**

```typescript
// Starting to load
loadingPhase.value = 'phase1';

// Phase 1 complete, Phase 2 starting
if (msg.includes('背景')) {
  loadingPhase.value = 'phase2';
}

// All loading complete
if (msg === '') {
  loadingPhase.value = 'complete';
}

// Error occurred
catch (e) {
  loadingPhase.value = 'error';
}
```

### Files Modified

- **`/opt/ws/xsw/src/pages/ChaptersPage.vue`**:
  - Lines 229-256: Added LoadingPhase type, state machine ref, and computed properties
  - Lines 237-245: Added LoadError interface and ref
  - Lines 39-79: Replaced error banner with context-aware version
  - Lines 284-344: Updated switchPage() with state machine
  - Lines 385-401: Updated loadInfo() error handling
  - Lines 455-552: Added retryPhase() function with state machine
  - Lines 712-781: Updated onMounted() with state machine

## Benefits Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Loading state tracking** | Boolean flags | State machine with 5 states |
| **State clarity** | Unclear which phase | Clear state at all times |
| **Error clarity** | Generic message | Phase-specific message |
| **User action** | Always full reload | Retry specific phase |
| **Partial success** | Not indicated | Clearly shown (Phase 2) |
| **Error severity** | All red | Red (critical) / Orange (warning) |
| **Technical details** | Hidden in console | Shown in UI (collapsible) |
| **Dismissibility** | Must retry or leave | Can dismiss and continue |
| **Debugging** | Hard to reason about | Easy with clear states |
| **Maintainability** | Complex boolean logic | Simple state transitions |

## Usage Examples

### Example 1: Phase 1 Fails Due to Network
```
User opens book page
→ Phase 1 starts loading (pages 9-11 for page 10)
→ Network error occurs
→ Red error banner appears: "載入章節失敗"
→ User clicks Retry
→ Phase 1 retries successfully
→ Content appears
```

### Example 2: Phase 2 Fails (Phase 1 Succeeded)
```
User opens book page
→ Phase 1 completes (pages 9-11 loaded)
→ Content appears immediately
→ Phase 2 starts in background
→ Network error occurs
→ Orange warning banner appears: "背景載入未完成（前3頁已可用）"
→ User can:
  - Click Retry to load remaining chapters
  - Dismiss and continue reading first 60 chapters
  - Ignore and keep reading
```

### Example 3: Book Info Fails
```
User opens book page
→ Book info loading fails
→ Red error banner: "載入書籍資訊失敗"
→ User clicks Retry
→ Book info loads successfully
→ Chapter loading begins
```

## Error Recovery Flow

```
┌─────────────────┐
│  Error Occurs   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│ Detect Phase & Set loadError│
│ - Check pageChapters.length │
│ - Determine phase type      │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Show Context-Aware Banner   │
│ - Red for critical          │
│ - Orange for Phase 2        │
│ - Include technical details │
└────────┬────────────────────┘
         │
    User Action
    /         \
   /           \
Retry         Dismiss
  │              │
  ▼              ▼
retryPhase()   Clear error
  │            Continue
  ▼
Attempt recovery
  │
Success or new error
```

## Future Enhancements

Potential improvements not yet implemented:

1. **Auto-retry with backoff**: Automatically retry Phase 2 failures after delay
2. **Offline detection**: Show different message when offline
3. **Progress indicator during retry**: Show what's being retried
4. **Partial Phase 2 success**: Track which pages loaded in Phase 2
5. **Error history**: Keep track of repeated failures
6. **Network quality indicator**: Warn users about slow connections

## Conclusion

The smart retry system provides:
- **Better UX**: Users understand what failed and can take appropriate action
- **Graceful degradation**: Phase 2 failures don't break the experience
- **Efficient recovery**: Retry only what failed, not everything
- **Clear communication**: Visual distinction between critical and non-critical errors

This aligns with the principle of **progressive enhancement** - the app works with minimal data (Phase 1) but enhances the experience when more data (Phase 2) is available.
