// src/services/bookApi.ts
import { api } from 'boot/axios';
import type { Category, BookSummary, BookInfo, Chapters, ChapterContent } from 'src/types/book-api';

export async function getHealth() {
  const { data } = await api.get('/health');
  return data;
}
export async function getCategories(): Promise<Category[]> {
  const { data } = await api.get('/categories');
  return data;
}
export async function listBooksInCategory(
  catId: number | string,
  page = 1,
): Promise<BookSummary[]> {
  const { data } = await api.get(`/categories/${catId}/books`, { params: { page } });
  return data;
}

function normalizeBookInfo(b: BookInfo): BookInfo & { last_chapter_number: number | null } {
  const n = b.last_chapter_number;
  return {
    ...b,
    last_chapter_number: Number.isFinite(n ?? NaN) ? (n as number) : null,
  };
}

export async function getBookInfo(bookId: string): Promise<BookInfo> {
  const { data } = await api.get(`/books/${bookId}`);
  return normalizeBookInfo(data);
}
export async function getBookChapters(
  bookId: string,
  opts?: { page?: number; all?: boolean; max_pages?: number; nocache?: boolean },
): Promise<Chapters> {
  // Use extended timeout for fetching all chapters (up to 5 minutes)
  const timeout = opts?.all ? 300000 : 15000;
  const { data } = await api.get(`/books/${bookId}/chapters`, {
    params: opts,
    timeout
  });
  return data;
}
export async function getChapterContent(
  bookId: string,
  chapterNum: number,
  nocache = false,
): Promise<ChapterContent> {
  // Use extended timeout for chapter content (up to 2 minutes for slow networks/scraping)
  const { data } = await api.get(`/books/${bookId}/chapters/${chapterNum}`, {
    params: { nocache },
    timeout: 120000, // 2 minutes
  });
  return data;
}
export async function searchBooks(q: string, page = 1): Promise<BookSummary[]> {
  const { data } = await api.get('/search', { params: { q, page } });
  return data;
}
