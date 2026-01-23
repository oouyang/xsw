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
        const start = (state.page - 1) * state.pageSize;
        const end = start + state.pageSize;
        return state.allChapters.slice(start, end);
      }

      const start = (state.page - 1) * state.pageSize;
      const end = start + state.pageSize;
      return state.pageChapters.slice(start, end);
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
        // Preserve new defaults when older payloads don’t have them
        this.$patch({
          ...saved,
          allChapters: saved.allChapters ?? [],
          pageChapters: saved.pageChapters ?? [], // migrate old `chapters` into `pageChapters` on first load
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
        const start = (this.page - 1) * this.pageSize;
        const end = start + this.pageSize;
        this.pageChapters = this.allChapters.slice(start, end);
        console.log(`[setPage] Sliced chapters ${start}-${end}, got ${this.pageChapters.length} chapters`);
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
        this.allChapters = firstPhaseMerged;

        // Derive current page slice for immediate display
        const start = (this.page - 1) * this.pageSize;
        const end = start + this.pageSize;
        this.pageChapters = this.allChapters.slice(start, end);
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
        const start = (this.page - 1) * this.pageSize;
        const end = start + this.pageSize;
        this.pageChapters = this.allChapters.slice(start, end);
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

        this.allChapters = merged;

        // Update current page slice if needed
        const start = (this.page - 1) * this.pageSize;
        const end = start + this.pageSize;
        this.pageChapters = this.allChapters.slice(start, end);

        console.log(
          `[loadRemainingChapters] Phase 2 complete: Total ${this.allChapters.length} chapters loaded`,
        );

        this.save();

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
        const start = (this.page - 1) * this.pageSize;
        const end = start + this.pageSize;
        this.pageChapters = this.allChapters.slice(start, end);
        this.save();
        return;
      }

      // Fallback: fetch the current page only
      const slice = await getBookChapters(this.bookId, {
        page: this.page,
        all: false,
      });

      this.pageChapters = Array.isArray(slice) ? slice : slice.chapters;

      this.save();
    },
  },
});
