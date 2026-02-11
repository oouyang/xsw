import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type { ChapterRef } from 'src/types/book-api';

// ── Mocks ─────────────────────────────────────────────────────

// Mock quasar LocalStorage (used by store.save()/load())
vi.mock('quasar', () => ({
  LocalStorage: {
    getItem: vi.fn(() => null),
    set: vi.fn(),
  },
}));

// Mock bookApi (breaks the boot/axios → #q-app/wrappers chain)
vi.mock('src/services/bookApi', () => ({
  getBookChapters: vi.fn(),
  getBookInfo: vi.fn(),
}));

// Mock useAppConfig (breaks circular import with utils.ts)
vi.mock('src/services/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { value: { bookId: 'test', featureFlags: {} } },
    update: vi.fn(),
  }),
}));

import { useBookStore } from 'src/stores/books';

// ── Helpers ───────────────────────────────────────────────────

function makeChapter(n: number, title?: string): ChapterRef {
  return { number: n, title: title ?? `Chapter ${n}`, url: `/ch/${n}` };
}

function makeChapters(start: number, end: number): ChapterRef[] {
  const chapters: ChapterRef[] = [];
  for (let i = start; i <= end; i++) {
    chapters.push(makeChapter(i));
  }
  return chapters;
}

// ──────────────────────────────────────────────────────────────
// setBookId
// ──────────────────────────────────────────────────────────────
describe('setBookId', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('clears all state when changing to a different book', () => {
    const store = useBookStore();
    store.bookId = 'old-book';
    store.allChapters = makeChapters(1, 50);
    store.pageChapters = makeChapters(1, 20);
    store.page = 3;
    store.info = { name: 'Old', author: '', type: '', status: '', update: '', last_chapter_title: '', last_chapter_url: '' };

    store.setBookId('new-book');

    expect(store.bookId).toBe('new-book');
    expect(store.allChapters).toEqual([]);
    expect(store.pageChapters).toEqual([]);
    expect(store.page).toBe(1);
    expect(store.info).toBeNull();
    expect(store.currentChapterIndex).toBeNull();
    expect(store.resyncRetries).toBe(0);
    expect(store.lastValidationError).toBeNull();
  });

  it('preserves cache when setting same book', () => {
    const store = useBookStore();
    store.bookId = 'same-book';
    const chapters = makeChapters(1, 50);
    store.allChapters = chapters;

    store.setBookId('same-book');

    // Pinia wraps in reactive proxy so toBe won't match; verify data preserved
    expect(store.allChapters).toHaveLength(50);
    expect(store.allChapters[0]!.number).toBe(1);
  });
});

// ──────────────────────────────────────────────────────────────
// BookInfo new optional fields (description, bookmark_count, view_count)
// ──────────────────────────────────────────────────────────────
describe('BookInfo new fields', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('stores and exposes description, bookmark_count, view_count', () => {
    const store = useBookStore();
    store.info = {
      name: 'Test', author: 'A', type: 'Fantasy', status: '連載中', update: '2026-01-01',
      last_chapter_title: 'Ch 10', last_chapter_url: '/ch/10', last_chapter_number: 10,
      description: 'A great novel about adventures.',
      bookmark_count: 5678,
      view_count: 123456,
    };

    expect(store.info.description).toBe('A great novel about adventures.');
    expect(store.info.bookmark_count).toBe(5678);
    expect(store.info.view_count).toBe(123456);
  });

  it('handles null/undefined new fields gracefully', () => {
    const store = useBookStore();
    store.info = {
      name: 'Test', author: 'A', type: '', status: '', update: '',
      last_chapter_title: '', last_chapter_url: '',
      description: null,
      bookmark_count: null,
      view_count: null,
    };

    expect(store.info.description).toBeNull();
    expect(store.info.bookmark_count).toBeNull();
    expect(store.info.view_count).toBeNull();
  });

  it('works without new fields (backward compat)', () => {
    const store = useBookStore();
    // BookInfo without the new optional fields (simulates old API response)
    store.info = {
      name: 'Old', author: 'B', type: '', status: '', update: '',
      last_chapter_title: '', last_chapter_url: '',
    };

    expect(store.info.name).toBe('Old');
    expect(store.info.description).toBeUndefined();
    expect(store.info.bookmark_count).toBeUndefined();
    expect(store.info.view_count).toBeUndefined();
  });

  it('setBookId clears info including new fields', () => {
    const store = useBookStore();
    store.bookId = 'old-book';
    store.info = {
      name: 'Old', author: '', type: '', status: '', update: '',
      last_chapter_title: '', last_chapter_url: '',
      description: 'Some description',
      bookmark_count: 100,
      view_count: 200,
    };

    store.setBookId('new-book');

    expect(store.info).toBeNull();
  });

  it('maxPages still works with info containing new fields', () => {
    const store = useBookStore();
    store.pageSize = 20;
    store.info = {
      name: 'Test', author: '', type: '', status: '', update: '',
      last_chapter_title: '', last_chapter_url: '',
      last_chapter_number: 100,
      description: 'Desc',
      bookmark_count: 42,
      view_count: 9999,
    };

    expect(store.maxPages).toBe(5); // 100 / 20
  });
});

// ──────────────────────────────────────────────────────────────
// setPage — CRITICAL: number-based filtering
// ──────────────────────────────────────────────────────────────
describe('setPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('derives pageChapters via number-based filtering', () => {
    const store = useBookStore();
    store.allChapters = makeChapters(1, 50);
    store.pageSize = 20;

    store.setPage(1);
    expect(store.pageChapters).toHaveLength(20);
    expect(store.pageChapters[0]!.number).toBe(1);
    expect(store.pageChapters[19]!.number).toBe(20);

    store.setPage(2);
    expect(store.pageChapters).toHaveLength(20);
    expect(store.pageChapters[0]!.number).toBe(21);
    expect(store.pageChapters[19]!.number).toBe(40);

    store.setPage(3);
    expect(store.pageChapters).toHaveLength(10); // chapters 41-50
    expect(store.pageChapters[0]!.number).toBe(41);
  });

  it('clamps page to minimum 1', () => {
    const store = useBookStore();
    store.allChapters = makeChapters(1, 10);

    store.setPage(0);
    expect(store.page).toBe(1);

    store.setPage(-5);
    expect(store.page).toBe(1);
  });

  it('works correctly with gaps in chapter numbers', () => {
    const store = useBookStore();
    // Gap: no chapter 2, no chapters 4-19
    store.allChapters = [
      makeChapter(1),
      makeChapter(3),
      makeChapter(20),
    ];
    store.pageSize = 20;

    store.setPage(1); // page 1 = chapters 1-20
    // All 3 chapters have numbers in range 1-20
    expect(store.pageChapters).toHaveLength(3);
    expect(store.pageChapters.map((c) => c.number)).toEqual([1, 3, 20]);
  });
});

// ──────────────────────────────────────────────────────────────
// setChapter
// ──────────────────────────────────────────────────────────────
describe('setChapter', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('finds chapter by number + title', () => {
    const store = useBookStore();
    store.allChapters = makeChapters(1, 10);

    store.setChapter({ number: 5, title: 'Chapter 5', url: '/ch/5' });
    expect(store.currentChapterIndex).toBe(4); // 0-indexed
  });

  it('falls back to number-only match when title differs', () => {
    const store = useBookStore();
    store.allChapters = makeChapters(1, 10);

    store.setChapter({ number: 5, title: 'Different Title', url: '/ch/5' });
    expect(store.currentChapterIndex).toBe(4);
  });

  it('sets -1 when chapter not found', () => {
    const store = useBookStore();
    store.allChapters = makeChapters(1, 10);

    store.setChapter({ number: 999, title: 'Missing', url: '/ch/999' });
    expect(store.currentChapterIndex).toBe(-1);
  });

  it('ignores null/undefined input', () => {
    const store = useBookStore();
    store.currentChapterIndex = 5;

    store.setChapter(null);
    expect(store.currentChapterIndex).toBe(5); // unchanged

    store.setChapter(undefined);
    expect(store.currentChapterIndex).toBe(5); // unchanged
  });
});

// ──────────────────────────────────────────────────────────────
// maxPages (getter)
// ──────────────────────────────────────────────────────────────
describe('maxPages', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('computes from info.last_chapter_number', () => {
    const store = useBookStore();
    store.pageSize = 20;
    store.info = {
      name: 'Test', author: '', type: '', status: '', update: '',
      last_chapter_title: '', last_chapter_url: '',
      last_chapter_number: 100,
    };

    expect(store.maxPages).toBe(5); // 100 / 20
  });

  it('computes from allChapters max number when no info', () => {
    const store = useBookStore();
    store.pageSize = 20;
    store.allChapters = makeChapters(1, 45);

    expect(store.maxPages).toBe(3); // ceil(45 / 20)
  });

  it('falls back to 1 when no data', () => {
    const store = useBookStore();
    expect(store.maxPages).toBe(1);
  });
});

// ──────────────────────────────────────────────────────────────
// pageSlice (getter)
// ──────────────────────────────────────────────────────────────
describe('pageSlice', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('returns pageChapters when set', () => {
    const store = useBookStore();
    const chapters = makeChapters(1, 5);
    store.pageChapters = chapters;

    expect(store.pageSlice).toEqual(chapters);
  });

  it('falls back to number-based filter from allChapters', () => {
    const store = useBookStore();
    store.pageSize = 20;
    store.page = 2;
    store.allChapters = makeChapters(1, 50);
    store.pageChapters = []; // empty — triggers fallback

    const slice = store.pageSlice;
    expect(slice).toHaveLength(20);
    expect(slice[0]!.number).toBe(21);
    expect(slice[19]!.number).toBe(40);
  });

  it('returns empty array when no data', () => {
    const store = useBookStore();
    expect(store.pageSlice).toEqual([]);
  });
});

// ──────────────────────────────────────────────────────────────
// nextChapter / prevChapter (getters)
// ──────────────────────────────────────────────────────────────
describe('nextChapter / prevChapter', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('returns next chapter', () => {
    const store = useBookStore();
    store.allChapters = makeChapters(1, 5);
    store.currentChapterIndex = 2; // Chapter 3

    expect(store.nextChapter).toEqual(makeChapter(4));
  });

  it('returns null at end boundary', () => {
    const store = useBookStore();
    store.allChapters = makeChapters(1, 5);
    store.currentChapterIndex = 4; // last chapter

    expect(store.nextChapter).toBeNull();
  });

  it('returns prev chapter', () => {
    const store = useBookStore();
    store.allChapters = makeChapters(1, 5);
    store.currentChapterIndex = 2; // Chapter 3

    expect(store.prevChapter).toEqual(makeChapter(2));
  });

  it('returns null at start boundary', () => {
    const store = useBookStore();
    store.allChapters = makeChapters(1, 5);
    store.currentChapterIndex = 0; // first chapter

    expect(store.prevChapter).toBeNull();
  });
});

// ──────────────────────────────────────────────────────────────
// validateChapters
// ──────────────────────────────────────────────────────────────
describe('validateChapters', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('returns error when no chapters loaded', () => {
    const store = useBookStore();
    store.allChapters = [];

    const result = store.validateChapters();
    expect(result.valid).toBe(false);
    expect(result.errors).toContain('No chapters loaded');
  });

  it('passes validation for sorted, complete chapters', () => {
    const store = useBookStore();
    store.allChapters = makeChapters(1, 100);
    store.info = {
      name: 'Test', author: '', type: '', status: '', update: '',
      last_chapter_title: '', last_chapter_url: '',
      last_chapter_number: 100,
    };

    const result = store.validateChapters();
    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it('returns error when chapters are not sorted', () => {
    const store = useBookStore();
    store.allChapters = [
      makeChapter(1),
      makeChapter(5),
      makeChapter(3), // out of order
    ];

    const result = store.validateChapters();
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('not sorted'))).toBe(true);
  });

  it('returns error when too few chapters vs expected', () => {
    const store = useBookStore();
    store.allChapters = makeChapters(1, 10); // only 10 chapters
    store.info = {
      name: 'Test', author: '', type: '', status: '', update: '',
      last_chapter_title: '', last_chapter_url: '',
      last_chapter_number: 1000, // expected 1000
    };

    const result = store.validateChapters();
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('Too few chapters'))).toBe(true);
  });

  it('returns warning (not error) for gaps in chapter numbers', () => {
    const store = useBookStore();
    store.allChapters = [
      makeChapter(1),
      makeChapter(2),
      makeChapter(5), // gap: 3, 4 missing
      makeChapter(6),
    ];

    const result = store.validateChapters();
    expect(result.valid).toBe(true); // gaps are warnings, not errors
    expect(result.warnings.some((w) => w.includes('Gap'))).toBe(true);
  });

  it('returns warning (not error) when first chapter is not 1', () => {
    const store = useBookStore();
    store.allChapters = [
      makeChapter(3),
      makeChapter(4),
      makeChapter(5),
    ];

    const result = store.validateChapters();
    expect(result.valid).toBe(true); // first != 1 is a warning
    expect(result.warnings.some((w) => w.includes('First chapter is 3'))).toBe(true);
  });
});
