import { defineStore } from 'pinia';
import { LocalStorage } from 'quasar';
import type { BookInfo, ChapterRef } from 'src/types/book-api';
import { dedupeBy, normalizeNum } from 'src/services/utils';
import { getBookChapters, getBookInfo } from 'src/services/bookApi';

export interface BookState {
  bookId: string | null;

  // book-base info from getBookInfo
  info: BookInfo | null;

  // GLOBAL cache: all chapters across all pages
  allChapters: ChapterRef[];

  // global chapter cache merged from multiple pages
  pageChapters: ChapterRef[];

  // UI state
  page: number; // current page (1..maxPages)
  currentChapterIndex: number | null; // last chapter user opened

  // pageSize (your API uses 20)
  pageSize: number;

  // Validation and retry tracking
  resyncRetries: number; // Number of resync attempts for current book
  lastValidationError: string | null; // Last validation error message
}

const STORAGE_KEY = 'bookStore:v1';

export const useBookStore = defineStore('book', {
  state: (): BookState => ({
    bookId: null,
    info: null,

    allChapters: [],

    pageChapters: [],
    page: 1,
    currentChapterIndex: -1,
    pageSize: 20,

    // Validation tracking
    resyncRetries: 0,
    lastValidationError: null,
  }),

  getters: {
    getChapterIndex(state): number {
      return state.currentChapterIndex ?? -1;
    },

    nextChapter(state): ChapterRef | null {
      const index = (state.currentChapterIndex ?? 0) + 1;

      if (index < 0 || index >= state.allChapters.length) return null;

      return state.allChapters.at(index) ?? null;
    },

    prevChapter(state): ChapterRef | null {
      const index = (state.currentChapterIndex ?? 1) - 1;
      if (index < 0 || index >= state.allChapters.length) return null;
      return state.allChapters.at(index) ?? null;
    },

    maxPages(state): number {
      // Priority 1: Use last_chapter_number from book info if available
      const lastFromInfo = state.info?.last_chapter_number ?? 0;
      if (lastFromInfo > 0) {
        return Math.ceil(lastFromInfo / state.pageSize);
      }

      // Priority 2: Use allChapters length if we have chapters loaded
      if (state.allChapters.length > 0) {
        const maxChapterNum = state.allChapters.reduce(
          (max, ch) => Math.max(max, ch.number),
          0
        );
        return Math.ceil(maxChapterNum / state.pageSize);
      }

      // Fallback: At least 1 page
      return 1;
    },

    /**
     * For compatibility: previously consumers used `pageSlice`.
     * Now it simply returns `pageChapters` when available;
     * otherwise slices from `allChapters` or the deprecated `chapters`.
     */
    pageSlice(state): ChapterRef[] {
      if (state.pageChapters.length > 0) return state.pageChapters;

      // Fallback to slicing allChapters if present
      if (state.allChapters.length > 0) {
        // ALWAYS use number-based filter to avoid assuming chapter.number = index + 1
        const currentPageFirstChapter = (state.page - 1) * state.pageSize + 1;
        const currentPageLastChapter = state.page * state.pageSize;
        return state.allChapters.filter(
          ch => ch.number >= currentPageFirstChapter && ch.number <= currentPageLastChapter
        );
      }

      return [];
    },
  },

  actions: {
    setChapter(chapter: ChapterRef | null | undefined) {
      if (!chapter) return;

      // First try to match by both number and title
      let index = this.allChapters.findIndex(
        (c) => c.number === chapter.number && c.title === chapter.title,
      );

      // If not found, try matching by number only (title might differ slightly)
      if (index === -1) {
        console.log(`[setChapter] Chapter not found by number+title, trying number only. Looking for: ${chapter.number} "${chapter.title}"`);
        index = this.allChapters.findIndex((c) => c.number === chapter.number);

        if (index !== -1) {
          console.log(`[setChapter] Found by number only at index ${index}: "${this.allChapters[index]?.title}"`);
        }
      }

      this.currentChapterIndex = index;
      console.log(`[setChapter] Set currentChapterIndex to ${index} for chapter ${chapter.number}`);
    },

    setCurrentChapterIndex(i: number | null) {
      this.currentChapterIndex = i;
      this.save();
    },
    /** Load persisted state (call in boot) */
    load() {
      const saved = LocalStorage.getItem<BookState>(STORAGE_KEY);
      if (saved) {
        // Preserve new defaults when older payloads don't have them
        this.$patch({
          ...saved,
          allChapters: saved.allChapters ?? [],
          pageChapters: saved.pageChapters ?? [], // migrate old `chapters` into `pageChapters` on first load
          resyncRetries: saved.resyncRetries ?? 0,
          lastValidationError: saved.lastValidationError ?? null,
        });
      }
      //this.$patch(saved);
    },

    /** Persist immediately */
    save() {
      LocalStorage.set(STORAGE_KEY, {
        bookId: this.bookId,
        info: this.info,

        allChapters: this.allChapters,
        pageChapters: this.pageChapters,

        page: this.page,
        currentChapterIndex: this.currentChapterIndex,
        pageSize: this.pageSize,

        resyncRetries: this.resyncRetries,
        lastValidationError: this.lastValidationError,
      });
    },

    /** When user selects a NEW book */
    setBookId(id: string) {
      console.log(`[setBookId] Changing from "${this.bookId}" to "${id}"`);
      if (this.bookId !== id) {
        console.log(`[setBookId] Different book detected, clearing cache (had ${this.allChapters.length} chapters)`);
        this.bookId = id;
        this.page = 1;
        this.info = null;

        this.allChapters = [];
        this.pageChapters = [];

        this.currentChapterIndex = null;

        // Reset validation tracking for new book
        this.resyncRetries = 0;
        this.lastValidationError = null;

        this.save();
      } else {
        console.log(`[setBookId] Same book, keeping cache (${this.allChapters.length} chapters)`);
      }
    },

    setInfo(info: BookInfo) {
      this.info = info;
      this.save();
    },

    /** Merge new chapters (dedupe by chapter number) */
    // mergeChapters(list: ChapterRef[]) {
    //   this.pageChapters = dedupeBy([...this.pageChapters, ...list], (c) => normalizeNum(c.number));

    //   this.pageChapters = sortByChapterNumber(merged);

    //   this.save();
    // },

    // /** Replace chapters fully (e.g., when API returns page slice) */
    // replaceChapters(list: ChapterRef[]) {
    //   this.pageChapters = [...list];
    //   this.save();
    // },

    setPage(p: number) {
      this.page = Math.max(1, p);
      console.log(`[setPage] Setting page to ${this.page}, allChapters: ${this.allChapters.length}`);

      if (this.allChapters.length > 0) {
        // ALWAYS use number-based filter to avoid assuming chapter.number = index + 1
        const currentPageFirstChapter = (this.page - 1) * this.pageSize + 1;
        const currentPageLastChapter = this.page * this.pageSize;
        this.pageChapters = this.allChapters.filter(
          ch => ch.number >= currentPageFirstChapter && ch.number <= currentPageLastChapter
        );
        console.log(`[setPage] Number-based filter for chapters ${currentPageFirstChapter}-${currentPageLastChapter}, got ${this.pageChapters.length} chapters`);
      } else {
        console.log(`[setPage] allChapters is empty, cannot slice`);
      }
      this.save();
    },

    /**
     * Load ALL chapters across all pages and cache them into `allChapters`.
     * Always derive `pageChapters` from `allChapters` afterwards.
     *
     * Two-phase loading for better UX:
     *   Phase 1: Load first 3 pages immediately (fast initial display)
     *   Phase 2: Load remaining chapters in background (non-blocking)
     *
     * Re-fetches when:
     *   - bookId changed OR
     *   - no cache OR
     *   - cache is outdated (based on `info.last_chapter_number`) OR
     *   - force == true
     */
    async loadAllChapters(opts?: { force?: boolean; onProgress?: (msg: string) => void }) {
      if (!this.bookId) throw new Error('[loadAllChapters] bookId is null');

      const expectedLast = this.info?.last_chapter_number ?? 0;
      const cachedLast =
        this.allChapters.length > 0
          ? this.allChapters.reduce((max, ch) => {
              const n = normalizeNum(ch.number);
              return Math.max(Number(n), max);
            }, 0)
          : 0;

      const isCacheOutdated =
        opts?.force === true ||
        this.allChapters.length === 0 ||
        (expectedLast > 0 && cachedLast < expectedLast) ||
        (expectedLast > 0 && this.allChapters.length < expectedLast); // Check total count, not just highest chapter

      if (isCacheOutdated) {
        if (expectedLast > 0 && cachedLast < expectedLast) {
          console.log(
            `[loadAllChapters] Cache outdated (has ${cachedLast}, expected ${expectedLast}), re-fetching all chapters`,
          );
        } else if (expectedLast > 0 && this.allChapters.length < expectedLast) {
          console.log(
            `[loadAllChapters] Incomplete cache (has ${this.allChapters.length} chapters, expected ${expectedLast}), re-fetching all chapters`,
          );
        } else if (this.allChapters.length === 0) {
          console.log('[loadAllChapters] No cache, fetching all chapters');
        } else if (opts?.force) {
          console.log('[loadAllChapters] Forced refresh, fetching all chapters');
        }

        // Two-phase loading strategy for better UX
        // Load current page + 1 before + 1 after = 3 pages total

        // Calculate which pages to load based on current page
        // Load: current page, previous page, and next page
        const currentPage = this.page;
        const pagesToFetch: number[] = [];

        // Add previous page (if exists)
        if (currentPage > 1) {
          pagesToFetch.push(currentPage - 1);
        }
        // Add current page
        pagesToFetch.push(currentPage);
        // Add next page
        pagesToFetch.push(currentPage + 1);

        // PHASE 1: Load pages around current page immediately
        if (opts?.onProgress) {
          opts.onProgress(`載入第 ${pagesToFetch[0]}-${pagesToFetch[pagesToFetch.length - 1]} 頁章節...`);
        }

        console.log(`[loadAllChapters] Phase 1: Loading pages ${pagesToFetch.join(', ')} around current page ${currentPage}`);

        // Fetch the selected pages in parallel
        const firstPhasePromises = pagesToFetch.map((page) =>
          getBookChapters(this.bookId!, { page, all: false })
        );

        const firstPhaseResponses = await Promise.all(firstPhasePromises);
        const firstPhaseChaptersList = firstPhaseResponses.flatMap((resp) =>
          Array.isArray(resp) ? resp : resp.chapters
        );

        // Dedupe and update state immediately with loaded pages
        const firstPhaseMerged = dedupeBy(firstPhaseChaptersList, (c) => normalizeNum(c.number));
        // CRITICAL: Sort by chapter number to ensure correct order
        firstPhaseMerged.sort((a, b) => a.number - b.number);
        this.allChapters = firstPhaseMerged;

        // Derive current page slice for immediate display
        // Calculate the chapter number range for current page
        const currentPageFirstChapter = (this.page - 1) * this.pageSize + 1;
        const currentPageLastChapter = this.page * this.pageSize;

        // Filter chapters that belong to the current page
        this.pageChapters = this.allChapters.filter(
          ch => ch.number >= currentPageFirstChapter && ch.number <= currentPageLastChapter
        );

        console.log(`[Phase 1] Current page ${this.page} should have chapters ${currentPageFirstChapter}-${currentPageLastChapter}, got ${this.pageChapters.length} chapters`);
        this.save();

        console.log(
          `[loadAllChapters] Phase 1 complete: Loaded ${this.allChapters.length} chapters from pages ${pagesToFetch.join(', ')}`,
        );

        // PHASE 2: Load remaining chapters in background (non-blocking)
        // Don't await this - let it run in the background
        void this.loadRemainingChapters(pagesToFetch, expectedLast, opts?.onProgress);

      } else {
        console.log(
          `[loadAllChapters] Using cached allChapters (${this.allChapters.length} chapters, last: ${cachedLast})`,
        );
        // even when using cache, always re-derive the current page view
        // ALWAYS use number-based filter to avoid assuming chapter.number = index + 1
        const currentPageFirstChapter = (this.page - 1) * this.pageSize + 1;
        const currentPageLastChapter = this.page * this.pageSize;
        this.pageChapters = this.allChapters.filter(
          ch => ch.number >= currentPageFirstChapter && ch.number <= currentPageLastChapter
        );
        this.save();
      }
    },

    /**
     * Phase 2: Load remaining chapters in background (non-blocking)
     * This runs asynchronously after the nearby pages are loaded.
     */
    async loadRemainingChapters(
      loadedPages: number[],
      expectedLast: number,
      onProgress?: (msg: string) => void
    ) {
      if (!this.bookId) return;

      // Calculate how many chapters we've loaded in phase 1
      const loadedChapters = loadedPages.length * this.pageSize;
      const remainingChapters = expectedLast - loadedChapters;

      if (remainingChapters <= 0) {
        console.log('[loadRemainingChapters] No remaining chapters to load');
        return;
      }

      console.log(`[loadRemainingChapters] Phase 2: Loading remaining ~${remainingChapters} chapters in background`);

      if (onProgress) {
        onProgress(`背景載入剩餘章節...`);
      }

      try {
        // Fetch all chapters using the all=true endpoint
        // The backend is optimized to handle this efficiently
        const allChaptersResponse = await getBookChapters(this.bookId, {
          all: true,
        });

        const chaptersArray = Array.isArray(allChaptersResponse)
          ? allChaptersResponse
          : allChaptersResponse.chapters;

        // Dedupe and merge with existing chapters
        const merged = dedupeBy(chaptersArray, (c) => normalizeNum(c.number));
        // CRITICAL: Sort by chapter number to ensure correct order
        merged.sort((a, b) => a.number - b.number);

        this.allChapters = merged;

        // Update current page slice
        // ALWAYS use number-based filter to avoid assuming chapter.number = index + 1
        const currentPageFirstChapter = (this.page - 1) * this.pageSize + 1;
        const currentPageLastChapter = this.page * this.pageSize;
        this.pageChapters = this.allChapters.filter(
          ch => ch.number >= currentPageFirstChapter && ch.number <= currentPageLastChapter
        );

        console.log(
          `[loadRemainingChapters] Phase 2 complete: Total ${this.allChapters.length} chapters loaded`,
        );

        this.save();

        // Validate chapters after loading all
        const validation = this.validateChapters();
        if (!validation.valid) {
          console.error('[loadRemainingChapters] Chapter validation failed:', validation.errors);
          // Trigger resync if validation fails
          void this.triggerResync(validation.errors.join('; '));
        }

        if (onProgress) {
          onProgress(''); // Clear progress message
        }
      } catch (error) {
        console.error('[loadRemainingChapters] Failed to load remaining chapters:', error);
        // Don't throw - this is a background operation, first 3 pages are already loaded
      }
    },

    async loadInfo(bookId: string): Promise<BookInfo> {
      this.info = await getBookInfo(bookId);
      return this.info;
    },

    /**
     * Ensure the page chapters are available.
     * If we already have `allChapters`, slice from it.
     * Otherwise, fetch ONLY the current page from the API.
     */
    async ensurePageChapters() {
      if (!this.bookId) throw new Error('[ensurePageChapters] bookId is null');

      if (this.allChapters.length > 0) {
        // ALWAYS use number-based filter to avoid assuming chapter.number = index + 1
        const currentPageFirstChapter = (this.page - 1) * this.pageSize + 1;
        const currentPageLastChapter = this.page * this.pageSize;
        this.pageChapters = this.allChapters.filter(
          ch => ch.number >= currentPageFirstChapter && ch.number <= currentPageLastChapter
        );
        this.save();
        return;
      }

      // Fallback: fetch the current page only
      const slice = await getBookChapters(this.bookId, {
        page: this.page,
        all: false,
      });

      const chapters = Array.isArray(slice) ? slice : slice.chapters;
      // Sort fetched chapters
      chapters.sort((a, b) => a.number - b.number);
      this.pageChapters = chapters;

      this.save();
    },

    /**
     * Validate chapters for reasonableness.
     * With sequential indexing (1, 2, 3, ...), checks for:
     * 1. Chapters are sorted by number
     * 2. No gaps (consecutive chapters, gap should always be 1)
     * 3. First chapter should be 1
     * 4. Total chapters should match expected count from book info
     *
     * @returns validation result { valid: boolean, errors: string[] }
     */
    validateChapters(): { valid: boolean; errors: string[] } {
      const errors: string[] = [];

      if (this.allChapters.length === 0) {
        errors.push('No chapters loaded');
        return { valid: false, errors };
      }

      // Check 1: Chapters should be sorted
      for (let i = 1; i < this.allChapters.length; i++) {
        const curr = this.allChapters[i];
        const prev = this.allChapters[i - 1];
        if (curr && prev && curr.number < prev.number) {
          errors.push(`Chapters not sorted: chapter ${prev.number} > ${curr.number} at index ${i}`);
          break; // Only report first sorting error
        }
      }

      // Check 2: No gaps (sequential chapters should be consecutive)
      // With sequential indexing, gap should always be 1
      for (let i = 1; i < this.allChapters.length; i++) {
        const curr = this.allChapters[i];
        const prev = this.allChapters[i - 1];
        if (curr && prev) {
          const gap = curr.number - prev.number;
          if (gap !== 1) {
            errors.push(`Gap detected: chapter ${prev.number} → ${curr.number} (gap: ${gap}, expected: 1)`);
            // Only report first 3 gaps to avoid spam
            if (errors.filter(e => e.includes('Gap detected')).length >= 3) break;
          }
        }
      }

      // Check 3: First chapter should be 1 (sequential indexing starts at 1)
      const firstChapter = this.allChapters[0]?.number ?? 0;
      if (firstChapter !== 1) {
        errors.push(`First chapter number is ${firstChapter} (expected: 1 for sequential indexing)`);
      }

      // Check 4: Total count should match book info
      if (this.info?.last_chapter_number) {
        const expectedCount = this.info.last_chapter_number;
        const actualCount = this.allChapters.length;
        const discrepancy = Math.abs(expectedCount - actualCount);

        // Allow 5% discrepancy or 10 chapters (whichever is larger)
        const tolerance = Math.max(Math.ceil(expectedCount * 0.05), 10);

        if (discrepancy > tolerance) {
          errors.push(`Chapter count mismatch: expected ${expectedCount}, got ${actualCount} (difference: ${discrepancy})`);
        }
      }

      const valid = errors.length === 0;
      console.log(`[validateChapters] Validation ${valid ? 'PASSED' : 'FAILED'}`, errors);

      return { valid, errors };
    },

    /**
     * Trigger resync for the current book.
     * Handles retry logic and sends email alert after 3 failed attempts.
     *
     * @param reason - Reason for resync (for logging and email)
     */
    async triggerResync(reason: string) {
      if (!this.bookId) {
        console.error('[triggerResync] No bookId, cannot resync');
        return;
      }

      const maxRetries = 3;
      this.resyncRetries++;
      this.lastValidationError = reason;
      this.save();

      console.log(`[triggerResync] Attempt ${this.resyncRetries}/${maxRetries} for book ${this.bookId}: ${reason}`);

      if (this.resyncRetries >= maxRetries) {
        // Max retries reached, send alert email
        console.error(`[triggerResync] Max retries (${maxRetries}) reached for book ${this.bookId}, sending alert email`);

        try {
          // Call backend to send alert email
          const response = await fetch(`/xsw/api/admin/alert/chapter-validation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              book_id: this.bookId,
              book_name: this.info?.name ?? 'Unknown',
              reason,
              retries: this.resyncRetries,
              last_chapter_number: this.info?.last_chapter_number ?? 0,
              actual_chapter_count: this.allChapters.length,
              to_email: 'owen.ouyang@live.com',
            }),
          });

          if (!response.ok) {
            console.error('[triggerResync] Failed to send alert email:', response.statusText);
          } else {
            console.log('[triggerResync] Alert email sent successfully');
          }
        } catch (error) {
          console.error('[triggerResync] Error sending alert email:', error);
        }

        return;
      }

      // Trigger resync via backend force-resync endpoint
      try {
        const response = await fetch(`/xsw/api/admin/jobs/force-resync/${this.bookId}?priority=10&clear_cache=true`, {
          method: 'POST',
        });

        if (!response.ok) {
          console.error('[triggerResync] Failed to queue resync:', response.statusText);
          return;
        }

        const result = await response.json();
        console.log('[triggerResync] Resync queued:', result);

        // Clear local cache and reload
        this.allChapters = [];
        this.pageChapters = [];
        this.save();

        // Wait a bit for backend to process, then reload
        // Use void operator to explicitly ignore the Promise from async function
        setTimeout(() => {
          void (async () => {
            console.log('[triggerResync] Reloading chapters after resync...');
            await this.loadAllChapters({ force: true });

            // Validate again after reload
            const validation = this.validateChapters();
            if (!validation.valid) {
              console.error('[triggerResync] Validation still failed after resync:', validation.errors);
              // Trigger another resync attempt
              await this.triggerResync(validation.errors.join('; '));
            } else {
              console.log('[triggerResync] Validation passed after resync!');
              // Reset retry counter on success
              this.resyncRetries = 0;
              this.lastValidationError = null;
              this.save();
            }
          })();
        }, 5000); // Wait 5 seconds for backend to process
      } catch (error) {
        console.error('[triggerResync] Error triggering resync:', error);
      }
    },
  },
});
