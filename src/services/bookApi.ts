// src/services/bookApi.ts
import { api } from 'boot/axios';
import type { Category, BookSummary, BookInfo, Chapters, ChapterContent, CommentEntry } from 'src/types/book-api';

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
  opts?: { page?: number; all?: boolean; max_pages?: number; nocache?: boolean; timeout?: number },
): Promise<Chapters> {
  // Use extended timeout for fetching all chapters
  // For books with thousands of chapters, this can take a long time (10-15 minutes)
  // For single page requests, use 60 seconds (scraping can be slow)
  const timeout = opts?.timeout ?? (opts?.all ? 900000 : 60000); // 15 minutes for all chapters
  const { data } = await api.get(`/books/${bookId}/chapters`, {
    params: opts,
    timeout
  });
  return data;
}
export async function getChapterContent(
  bookId: string,
  chapterId: string,
  nocache = false,
): Promise<ChapterContent> {
  // Use extended timeout for chapter content (up to 2 minutes for slow networks/scraping)
  const { data } = await api.get(`/books/${bookId}/chapters/${chapterId}`, {
    params: { nocache },
    timeout: 120000, // 2 minutes
  });
  return data;
}
export async function searchBooks(q: string, page = 1): Promise<BookSummary[]> {
  const { data } = await api.get('/search', { params: { q, page } });
  return data;
}
export async function listBooksByAuthor(authorName: string): Promise<BookSummary[]> {
  const { data } = await api.get(`/authors/${encodeURIComponent(authorName)}/books`);
  return data;
}
export async function getSimilarBooks(bookId: string): Promise<BookSummary[]> {
  const { data } = await api.get(`/books/${bookId}/similar`);
  return data;
}
export async function getBookComments(bookId: string, page = 1): Promise<CommentEntry[]> {
  const { data } = await api.get(`/books/${bookId}/comments`, { params: { page } });
  return data;
}
