// src/types/book-api.ts
export interface Category {
  id: string;
  name: string;
  url: string;
}
export interface BookSummary {
  bookname: string;
  author: string;
  lastchapter: string;
  lasturl: string;
  intro: string;
  bookurl: string;
  book_id?: string | null;
  public_id?: string | null;
  bookmark_count?: number | null;
  view_count?: number | null;
}
export interface BookInfo {
  name: string;
  author: string;
  type: string;
  status: string;
  update: string;
  description?: string | null;
  bookmark_count?: number | null;
  view_count?: number | null;
  last_chapter_title: string;
  last_chapter_url: string;
  last_chapter_number?: number | null;
  book_id?: string | null;
  public_id?: string | null;
}
export interface ChapterRef {
  number: number;
  title: string;
  url: string;
  id?: string | null;
}
export interface Chapters {
  chapters: ChapterRef[];
  totalPages?: number;
}
export interface ChapterContent {
  book_id?: string | null;
  chapter_num?: number | null;
  title?: string | null;
  url: string;
  text: string;
  chapter_id?: string | null;
}
