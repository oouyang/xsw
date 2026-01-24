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
      const last = state.info?.last_chapter_number ?? 0;

      const total = last && last > 0 ? last : state.allChapters.length;

      return last > 0 ? Math.ceil(total / state.pageSize) : 1;
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
      this.currentChapterIndex = this.allChapters.findIndex(
        (c) => c.number === chapter.number && c.title === chapter.title,
      );
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
      if (this.bookId !== id) {
        this.bookId = id;
        this.page = 1;
        this.info = null;

        this.allChapters = [];
        this.pageChapters = [];

        this.currentChapterIndex = null;
        this.save();
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

      if (this.allChapters.length > 0) {
        const start = (this.page - 1) * this.pageSize;
        const end = start + this.pageSize;
        this.pageChapters = this.allChapters.slice(start, end);
      }
      this.save();
    },

    /**
     * Load ALL chapters across all pages and cache them into `allChapters`.
     * Always derive `pageChapters` from `allChapters` afterwards.
     *
     * Re-fetches when:
     *   - bookId changed OR
     *   - no cache OR
     *   - cache is outdated (based on `info.last_chapter_number`) OR
     *   - force == true
     */
    async loadAllChapters(opts?: { force?: boolean }) {
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
        (expectedLast > 0 && cachedLast < expectedLast);

      if (isCacheOutdated) {
        if (expectedLast > 0 && cachedLast < expectedLast) {
          console.log(
            `[loadAllChapters] Cache outdated (has ${cachedLast}, expected ${expectedLast}), re-fetching all chapters`,
          );
        } else if (this.allChapters.length === 0) {
          console.log('[loadAllChapters] No cache, fetching all chapters');
        } else if (opts?.force) {
          console.log('[loadAllChapters] Forced refresh, fetching all chapters');
        }

        const totalPages = this.maxPages;
        const requests: Promise<ChapterRef[]>[] = [];
        for (let i = 0; i < totalPages; i++) {
          const lastPageChapters = await getBookChapters(this.bookId, {
            page: i + 1,
            all: false,
          });

          const chaptersArray = Array.isArray(lastPageChapters)
            ? lastPageChapters
            : lastPageChapters.chapters;
          requests.push(...chaptersArray);
        }

        const results = await Promise.all(requests);
        const flattened = results.flat();

        const merged = dedupeBy(flattened, (c) => normalizeNum(c.number));
        const sorted = merged;

        this.allChapters = sorted;

        // derive current page slice
        const start = (this.page - 1) * this.pageSize;
        const end = start + this.pageSize;
        this.pageChapters = this.allChapters.slice(start, end);

        console.log(
          `[loadAllChapters] Fetched ${this.allChapters.length} chapters across ${totalPages} pages`,
        );

        this.save();
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
