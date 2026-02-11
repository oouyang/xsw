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

const STORAGE_KEY = 'bookStore:v2';
const STORAGE_KEY_OLD = 'bookStore:v1';

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

      // First try to match by public_id if available
      let index = -1;
      if (chapter.id) {
        index = this.allChapters.findIndex((c) => c.id === chapter.id);
      }

      // Then try by both number and title
      if (index === -1) {
        index = this.allChapters.findIndex(
          (c) => c.number === chapter.number && c.title === chapter.title,
        );
      }

      // If not found, try matching by number only (title might differ slightly)
      if (index === -1) {
        console.log(`[setChapter] Chapter not found by id/number+title, trying number only. Looking for: ${chapter.number} "${chapter.title}"`);
        index = this.allChapters.findIndex((c) => c.number === chapter.number);

        if (index !== -1) {
          console.log(`[setChapter] Found by number only at index ${index}: "${this.allChapters[index]?.title}"`);
        }
      }

      this.currentChapterIndex = index;
      console.log(`[setChapter] Set currentChapterIndex to ${index} for chapter ${chapter.number}`);
    },

    /**
     * Find a chapter by its public_id (string).
     * Falls back to finding by sequential number if input is numeric.
     */
    findChapterById(chapterId: string): ChapterRef | null {
      // Try matching by public_id first
      const byId = this.allChapters.find((c) => c.id === chapterId);
      if (byId) return byId;

      // Fall back to sequential number
      const num = Number(chapterId);
      if (Number.isFinite(num)) {
        return this.allChapters.find((c) => c.number === num) ?? null;
      }

      return null;
    },

    setCurrentChapterIndex(i: number | null) {
      this.currentChapterIndex = i;
      this.save();
    },
    /** Load persisted state (call in boot) */
    load() {
      // Remove stale v1 cache (had czbooks IDs, no chapter public_ids)
      LocalStorage.remove(STORAGE_KEY_OLD);

      const saved = LocalStorage.getItem<BookState>(STORAGE_KEY);
      if (saved) {
        // Preserve new defaults when older payloads don't have them
        this.$patch({
          ...saved,
          allChapters: saved.allChapters ?? [],
          pageChapters: saved.pageChapters ?? [],
          resyncRetries: saved.resyncRetries ?? 0,
          lastValidationError: saved.lastValidationError ?? null,
        });
      }
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
    async loadAllChapters(opts?: { force?: boolean; nocache?: boolean; onProgress?: (msg: string) => void }) {
      if (!this.bookId) throw new Error('[loadAllChapters] bookId is null');
      const bookId = this.bookId; // Capture in local variable for better type narrowing

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

        // Fetch the selected pages in parallel with extended timeout
        // Use allSettled so if one page fails, others can still succeed
        const firstPhasePromises = pagesToFetch.map((page) => {
          const reqOpts: Parameters<typeof getBookChapters>[1] = { page, all: false, timeout: 60000 };
          if (opts?.nocache !== undefined) reqOpts.nocache = opts.nocache;
          return getBookChapters(bookId, reqOpts);
        });

        const firstPhaseResults = await Promise.allSettled(firstPhasePromises);

        // Extract successful responses and log failures
        const firstPhaseResponses = firstPhaseResults
          .map((result, idx) => {
            if (result.status === 'fulfilled') {
              return result.value;
            } else {
              console.warn(`[Phase 1] Failed to load page ${pagesToFetch[idx]}:`, result.reason);
              return null;
            }
          })
          .filter((resp): resp is NonNullable<typeof resp> => resp !== null);

        // If all pages failed, try loading just the current page with retry
        if (firstPhaseResponses.length === 0) {
          console.warn('[Phase 1] All pages failed, retrying current page only...');
          if (opts?.onProgress) {
            opts.onProgress(`重試載入第 ${currentPage} 頁...`);
          }
          try {
            const retryOpts: Parameters<typeof getBookChapters>[1] = {
              page: currentPage,
              all: false,
              timeout: 90000 // 90 second timeout for retry
            };
            if (opts?.nocache !== undefined) retryOpts.nocache = opts.nocache;
            const currentPageResp = await getBookChapters(bookId, retryOpts);
            firstPhaseResponses.push(currentPageResp);
          } catch (retryError) {
            console.error('[Phase 1] Retry failed:', retryError);
            throw retryError; // Re-throw so the error is handled properly
          }
        }

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
        void this.loadRemainingChapters(pagesToFetch, expectedLast, opts?.onProgress, opts?.nocache);

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
      onProgress?: (msg: string) => void,
      nocache?: boolean
    ) {
      if (!this.bookId) return;
      const bookId = this.bookId; // Capture in local variable for better type narrowing

      // Calculate how many chapters we've loaded in phase 1
      const loadedChapters = loadedPages.length * this.pageSize;
      const remainingChapters = expectedLast - loadedChapters;

      if (remainingChapters <= 0) {
        console.log('[loadRemainingChapters] No remaining chapters to load');
        return;
      }

      console.log(`[loadRemainingChapters] Phase 2: Loading remaining ~${remainingChapters} chapters in background`);

      if (onProgress) {
        // Show different message for books with many chapters
        if (expectedLast > 2000) {
          onProgress(`背景載入剩餘章節... (此書共${expectedLast}章，可能需要10-15分鐘)`);
        } else {
          onProgress(`背景載入剩餘章節...`);
        }
      }

      try {
        // Fetch all chapters using the all=true endpoint
        // The backend is optimized to handle this efficiently
        const allOpts: Parameters<typeof getBookChapters>[1] = { all: true };
        if (nocache !== undefined) allOpts.nocache = nocache;

        console.log(`[loadRemainingChapters] Fetching all chapters (nocache=${allOpts.nocache ?? false})...`);
        const allChaptersResponse = await getBookChapters(bookId, allOpts);

        const chaptersArray = Array.isArray(allChaptersResponse)
          ? allChaptersResponse
          : allChaptersResponse.chapters;

        console.log(`[loadRemainingChapters] Received ${chaptersArray.length} chapters from backend`);

        // Check if we got a reasonable number of chapters
        // If we only got <20 chapters when expecting hundreds/thousands, the cache is stale
        if (chaptersArray.length < 20 && expectedLast > 100 && !nocache) {
          console.warn(`[loadRemainingChapters] Received only ${chaptersArray.length} chapters, but expected ${expectedLast}. Retrying with nocache=true...`);

          if (onProgress) {
            onProgress(`快取資料不完整，重新載入全部章節...`);
          }

          // Retry with nocache to force backend to re-scrape
          const retryOpts: Parameters<typeof getBookChapters>[1] = { all: true, nocache: true };
          const retryResponse = await getBookChapters(bookId, retryOpts);
          const retryChapters = Array.isArray(retryResponse) ? retryResponse : retryResponse.chapters;

          console.log(`[loadRemainingChapters] Retry with nocache returned ${retryChapters.length} chapters`);

          // Use retry result if it has more chapters
          if (retryChapters.length > chaptersArray.length) {
            chaptersArray.length = 0;
            chaptersArray.push(...retryChapters);
            console.log(`[loadRemainingChapters] Using retry result with ${retryChapters.length} chapters`);
          } else {
            console.warn(`[loadRemainingChapters] Retry did not improve result (still ${retryChapters.length} chapters)`);
          }
        }

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

        // Validate chapters after loading all (just log, don't auto-retry)
        const validation = this.validateChapters();
        if (!validation.valid) {
          console.error('[loadRemainingChapters] Chapter validation failed:', validation.errors);
          console.warn('[loadRemainingChapters] Auto-retry disabled - user can manually refresh if needed');
          // Note: Auto-retry is disabled because it often makes things worse
          // (e.g., clearing cache and reloading can result in fewer chapters)
          // Users can manually retry via the UI refresh button if needed
        } else {
          // Reset retry counter when validation passes
          this.resyncRetries = 0;
          this.lastValidationError = null;
          this.save();
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
      // Switch bookId to public_id once the API returns it,
      // so all future navigation uses our random ID instead of czbooks ID
      if (this.info.public_id && this.bookId !== this.info.public_id) {
        console.log(`[loadInfo] Switching bookId from "${this.bookId}" to public_id "${this.info.public_id}"`);
        this.bookId = this.info.public_id;
        this.save();
      }
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
     *
     * RELAXED VALIDATION: Only check critical issues that affect functionality.
     * Small gaps and discrepancies are normal due to source website issues.
     *
     * Critical issues:
     * 1. No chapters loaded at all
     * 2. Very few chapters (< 50% of expected)
     * 3. Chapters not sorted
     *
     * Non-critical (logged but not failed):
     * - Small gaps in chapter numbers
     * - First chapter not starting at 1
     * - Minor count discrepancies
     *
     * @returns validation result { valid: boolean, errors: string[] }
     */
    validateChapters(): { valid: boolean; errors: string[]; warnings: string[] } {
      const errors: string[] = [];
      const warnings: string[] = [];

      // CRITICAL: Check if any chapters loaded
      if (this.allChapters.length === 0) {
        errors.push('No chapters loaded');
        return { valid: false, errors, warnings };
      }

      // CRITICAL: Check if chapters are sorted
      for (let i = 1; i < this.allChapters.length; i++) {
        const curr = this.allChapters[i];
        const prev = this.allChapters[i - 1];
        if (curr && prev && curr.number < prev.number) {
          errors.push(`Chapters not sorted: chapter ${prev.number} > ${curr.number} at index ${i}`);
          break;
        }
      }

      // WARNING: Check for gaps (log but don't fail)
      let gapCount = 0;
      for (let i = 1; i < this.allChapters.length; i++) {
        const curr = this.allChapters[i];
        const prev = this.allChapters[i - 1];
        if (curr && prev) {
          const gap = curr.number - prev.number;
          if (gap > 1) {
            gapCount++;
            if (gapCount <= 3) { // Only log first 3 gaps
              warnings.push(`Gap: chapter ${prev.number} → ${curr.number} (gap: ${gap})`);
            }
          }
        }
      }
      if (gapCount > 3) {
        warnings.push(`... and ${gapCount - 3} more gaps`);
      }

      // WARNING: Check first chapter (log but don't fail)
      const firstChapter = this.allChapters[0]?.number ?? 0;
      if (firstChapter !== 1) {
        warnings.push(`First chapter is ${firstChapter} (expected: 1)`);
      }

      // CRITICAL: Check if we have enough chapters (at least 30% of expected)
      // Note: Some books have incorrect metadata on source website
      if (this.info?.last_chapter_number) {
        const expectedCount = this.info.last_chapter_number;
        const actualCount = this.allChapters.length;
        const percentage = (actualCount / expectedCount) * 100;

        // Require at least some reasonable minimum chapters to be useful
        const minRequiredChapters = Math.min(expectedCount * 0.3, 100); // At least 30% or 100 chapters

        if (actualCount < minRequiredChapters) {
          // Less than minimum - critical error
          errors.push(`Too few chapters: expected ${expectedCount}, got ${actualCount} (${percentage.toFixed(1)}%)`);
        } else if (Math.abs(expectedCount - actualCount) > Math.max(Math.ceil(expectedCount * 0.2), 50)) {
          // 20%+ discrepancy - warning only
          warnings.push(`Chapter count difference: expected ${expectedCount}, got ${actualCount} (${percentage.toFixed(1)}%)`);
        }
      }

      const valid = errors.length === 0;

      if (warnings.length > 0) {
        console.warn(`[validateChapters] Warnings (${warnings.length}):`, warnings);
      }

      if (!valid) {
        console.error(`[validateChapters] Validation FAILED:`, errors);
      } else {
        console.log(`[validateChapters] Validation PASSED (${this.allChapters.length} chapters)`);
      }

      return { valid, errors, warnings };
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

      // Force reload from backend with nocache=true (bypass all caches)
      try {
        console.log('[triggerResync] Clearing cache and reloading chapters...');

        // Clear local cache
        this.allChapters = [];
        this.pageChapters = [];
        this.save();

        // Reload with nocache to force backend to re-scrape
        console.log('[triggerResync] Fetching fresh chapters with nocache=true...');
        await this.loadAllChapters({ force: true, nocache: true });

        // Validate again after reload
        const validation = this.validateChapters();
        if (!validation.valid) {
          console.error('[triggerResync] Validation still failed after resync:', validation.errors);
          // Trigger another resync attempt (will retry up to maxRetries)
          await this.triggerResync(validation.errors.join('; '));
        } else {
          console.log('[triggerResync] Validation passed after resync!');
          // Reset retry counter on success
          this.resyncRetries = 0;
          this.lastValidationError = null;
          this.save();
        }
      } catch (error) {
        console.error('[triggerResync] Failed to reload chapters:', error);
      }
    },
  },
});
