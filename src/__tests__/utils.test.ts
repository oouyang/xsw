import { describe, it, expect, vi } from 'vitest';

// Mock quasar (imported transitively by utils.ts via Dialog/Dark)
vi.mock('quasar', () => ({
  Dialog: { create: vi.fn() },
  Dark: { toggle: vi.fn(), set: vi.fn(), isActive: false },
  LocalStorage: { getItem: vi.fn(), set: vi.fn() },
}));

// Mock useAppConfig (imported by utils.ts)
vi.mock('src/services/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { value: { bookId: 'test', featureFlags: {} } },
    update: vi.fn(),
  }),
}));

import { toArr, dedupeBy, normalizeNum, syncLastChapter } from 'src/services/utils';

// ──────────────────────────────────────────────────────────────
// toArr
// ──────────────────────────────────────────────────────────────
describe('toArr', () => {
  it('returns [] for null', () => {
    expect(toArr(null)).toEqual([]);
  });

  it('returns [] for undefined', () => {
    expect(toArr(undefined)).toEqual([]);
  });

  it('wraps a single value in an array', () => {
    expect(toArr(42)).toEqual([42]);
  });

  it('passes through an existing array unchanged', () => {
    const arr = [1, 2, 3];
    expect(toArr(arr)).toBe(arr); // same reference
  });
});

// ──────────────────────────────────────────────────────────────
// dedupeBy
// ──────────────────────────────────────────────────────────────
describe('dedupeBy', () => {
  it('removes duplicates by key function', () => {
    const items = [
      { id: 1, name: 'a' },
      { id: 2, name: 'b' },
      { id: 1, name: 'c' },
    ];
    const result = dedupeBy(items, (x) => x.id);
    expect(result).toEqual([
      { id: 1, name: 'a' },
      { id: 2, name: 'b' },
    ]);
  });

  it('returns empty array for empty input', () => {
    expect(dedupeBy([], (x: number) => x)).toEqual([]);
  });

  it('returns all items when no duplicates', () => {
    const items = [{ id: 1 }, { id: 2 }, { id: 3 }];
    const result = dedupeBy(items, (x) => x.id);
    expect(result).toEqual(items);
  });

  it('preserves first occurrence', () => {
    const items = [
      { id: 'a', val: 'first' },
      { id: 'a', val: 'second' },
    ];
    const result = dedupeBy(items, (x) => x.id);
    expect(result).toHaveLength(1);
    expect(result[0]!.val).toBe('first');
  });
});

// ──────────────────────────────────────────────────────────────
// normalizeNum
// ──────────────────────────────────────────────────────────────
describe('normalizeNum', () => {
  it('converts number to string', () => {
    expect(normalizeNum(42)).toBe('42');
  });

  it('passes through string unchanged', () => {
    expect(normalizeNum('100')).toBe('100');
  });
});

// ──────────────────────────────────────────────────────────────
// syncLastChapter
// ──────────────────────────────────────────────────────────────
describe('syncLastChapter', () => {
  const makeChapters = (nums: number[]) =>
    nums.map((n) => ({ number: n, title: `Ch ${n}`, url: `/ch/${n}` }));

  it('returns bookInfo unchanged when chapters is empty', () => {
    const info = { last_chapter_number: 10 };
    expect(syncLastChapter(info, [])).toBe(info);
  });

  it('syncs up when actual last chapter is higher', () => {
    const info = { last_chapter_number: 5, last_chapter_title: 'Ch 5', last_chapter_url: '/ch/5' };
    const chapters = makeChapters([1, 2, 3, 10]);
    const result = syncLastChapter(info, chapters);
    expect(result.last_chapter_number).toBe(10);
    expect(result.last_chapter_title).toBe('Ch 10');
    expect(result.last_chapter_url).toBe('/ch/10');
  });

  it('syncs down when actual last chapter is lower', () => {
    const info = { last_chapter_number: 100, last_chapter_title: 'Ch 100', last_chapter_url: '/ch/100' };
    const chapters = makeChapters([1, 2, 3]);
    const result = syncLastChapter(info, chapters);
    expect(result.last_chapter_number).toBe(3);
  });

  it('returns same reference when already in sync', () => {
    const info = { last_chapter_number: 3, last_chapter_title: 'Ch 3', last_chapter_url: '/ch/3' };
    const chapters = makeChapters([1, 2, 3]);
    const result = syncLastChapter(info, chapters);
    expect(result).toBe(info); // same reference, no mutation
  });
});
