// src/composables/useReadingHistory.ts
import { ref } from 'vue';
import type { ReadingHistoryEntry } from 'src/types/book-api';
import { userAuthService } from 'src/services/userAuthService';

const STORAGE_KEY = 'xsw_reading_history';
const MAX_ENTRIES = 20;

const history = ref<ReadingHistoryEntry[]>(loadFromStorage());

function loadFromStorage(): ReadingHistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const entries: ReadingHistoryEntry[] = JSON.parse(raw);
    return entries.sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_ENTRIES);
  } catch {
    return [];
  }
}

function saveToStorage(entries: ReadingHistoryEntry[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // localStorage full or unavailable
  }
}

export function useReadingHistory() {
  function updateProgress(entry: ReadingHistoryEntry) {
    const entries = [...history.value];
    const idx = entries.findIndex((e) => e.bookId === entry.bookId);

    if (idx >= 0) {
      entries[idx] = entry;
    } else {
      entries.unshift(entry);
    }

    // Sort by updatedAt DESC, limit to MAX_ENTRIES
    entries.sort((a, b) => b.updatedAt - a.updatedAt);
    history.value = entries.slice(0, MAX_ENTRIES);
    saveToStorage(history.value);

    // Fire-and-forget server sync if logged in
    if (userAuthService.isAuthenticated()) {
      void userAuthService.saveProgress(entry.bookId, {
        chapter_number: entry.chapterNumber,
        chapter_title: entry.chapterTitle,
        chapter_id: entry.chapterId,
        book_name: entry.bookName,
      }).catch(() => {
        // Best effort — don't block UI
      });
    }
  }

  function getHistory(): ReadingHistoryEntry[] {
    return history.value;
  }

  function clearHistory() {
    history.value = [];
    saveToStorage([]);

    // Clear server progress if logged in
    if (userAuthService.isAuthenticated()) {
      // Can't easily delete all at once, but we clear local
      // Server data will be stale until next sync
    }
  }

  function removeEntry(bookId: string) {
    history.value = history.value.filter((e) => e.bookId !== bookId);
    saveToStorage(history.value);
  }

  /**
   * Merge local history with server data on login.
   * For each book, whichever has a newer timestamp wins.
   */
  async function syncOnLogin() {
    if (!userAuthService.isAuthenticated()) return;

    try {
      const serverProgress = await userAuthService.listProgress();
      const localEntries = [...history.value];
      const merged = new Map<string, ReadingHistoryEntry>();

      // Add all local entries
      for (const entry of localEntries) {
        merged.set(entry.bookId, entry);
      }

      // Merge server entries — server wins if newer
      for (const sp of serverProgress) {
        const serverTime = new Date(sp.updated_at).getTime();
        const existing = merged.get(sp.book_id);

        if (!existing || serverTime > existing.updatedAt) {
          merged.set(sp.book_id, {
            bookId: sp.book_id,
            bookName: sp.book_name || '',
            chapterNumber: sp.chapter_number,
            chapterTitle: sp.chapter_title || '',
            chapterId: sp.chapter_id || '',
            totalChapters: 0, // Unknown from server
            updatedAt: serverTime,
          });
        } else if (existing && existing.updatedAt > serverTime) {
          // Local is newer — push to server
          void userAuthService.saveProgress(existing.bookId, {
            chapter_number: existing.chapterNumber,
            chapter_title: existing.chapterTitle,
            chapter_id: existing.chapterId,
            book_name: existing.bookName,
          }).catch(() => {});
        }
      }

      const sorted = Array.from(merged.values())
        .sort((a, b) => b.updatedAt - a.updatedAt)
        .slice(0, MAX_ENTRIES);

      history.value = sorted;
      saveToStorage(sorted);
    } catch {
      // Sync failed — keep local data
    }
  }

  return {
    history,
    updateProgress,
    getHistory,
    clearHistory,
    removeEntry,
    syncOnLogin,
  };
}
