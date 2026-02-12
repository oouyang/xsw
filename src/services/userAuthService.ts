// src/services/userAuthService.ts
import { api } from 'boot/axios';
import type {
  UserAuthResponse,
  UserProfile,
  ReadingProgressEntry,
} from 'src/types/book-api';

const TOKEN_KEY = 'xsw_user_token';

class UserAuthService {
  private token: string | null = null;
  private user: UserProfile | null = null;

  constructor() {
    this.loadFromStorage();
  }

  private loadFromStorage() {
    try {
      const stored = localStorage.getItem(TOKEN_KEY);
      if (stored) {
        const data = JSON.parse(stored);
        this.token = data.token;
        this.user = data.user;
      }
    } catch {
      this.clearAuth();
    }
  }

  private saveToStorage(token: string, user: UserProfile) {
    this.token = token;
    this.user = user;
    localStorage.setItem(TOKEN_KEY, JSON.stringify({ token, user }));
  }

  // --- Auth endpoints ---

  async loginWithGoogle(idToken: string): Promise<UserAuthResponse> {
    const { data } = await api.post<UserAuthResponse>('/user/auth/google', {
      id_token: idToken,
    });
    this.saveToStorage(data.access_token, data.user);
    return data;
  }

  async loginWithFacebook(accessToken: string): Promise<UserAuthResponse> {
    const { data } = await api.post<UserAuthResponse>('/user/auth/facebook', {
      access_token: accessToken,
    });
    this.saveToStorage(data.access_token, data.user);
    return data;
  }

  async loginWithApple(idToken: string, authorizationCode?: string): Promise<UserAuthResponse> {
    const { data } = await api.post<UserAuthResponse>('/user/auth/apple', {
      id_token: idToken,
      authorization_code: authorizationCode,
    });
    this.saveToStorage(data.access_token, data.user);
    return data;
  }

  async loginWithWeChat(code: string): Promise<UserAuthResponse> {
    const { data } = await api.post<UserAuthResponse>('/user/auth/wechat', {
      code,
    });
    this.saveToStorage(data.access_token, data.user);
    return data;
  }

  async verifyToken(): Promise<boolean> {
    if (!this.token) return false;
    try {
      await api.get('/user/auth/verify', {
        headers: this.getAuthHeaders(),
      });
      return true;
    } catch {
      this.clearAuth();
      return false;
    }
  }

  async getProfile(): Promise<UserProfile> {
    const { data } = await api.get<UserProfile>('/user/auth/me', {
      headers: this.getAuthHeaders(),
    });
    return data;
  }

  // --- Progress endpoints ---

  async listProgress(): Promise<ReadingProgressEntry[]> {
    const { data } = await api.get<ReadingProgressEntry[]>('/user/progress', {
      headers: this.getAuthHeaders(),
    });
    return data;
  }

  async getProgress(bookId: string): Promise<ReadingProgressEntry | null> {
    try {
      const { data } = await api.get<ReadingProgressEntry>(
        `/user/progress/${bookId}`,
        { headers: this.getAuthHeaders() },
      );
      return data;
    } catch {
      return null;
    }
  }

  async saveProgress(
    bookId: string,
    progress: {
      chapter_number: number;
      chapter_title?: string;
      chapter_id?: string;
      book_name?: string;
      scroll_position?: number;
    },
  ): Promise<ReadingProgressEntry> {
    const { data } = await api.put<ReadingProgressEntry>(
      `/user/progress/${bookId}`,
      progress,
      { headers: this.getAuthHeaders() },
    );
    return data;
  }

  async deleteProgress(bookId: string): Promise<void> {
    await api.delete(`/user/progress/${bookId}`, {
      headers: this.getAuthHeaders(),
    });
  }

  // --- Token management ---

  getAuthHeaders(): Record<string, string> {
    if (!this.token) return {};
    return { Authorization: `Bearer ${this.token}` };
  }

  getToken(): string | null {
    return this.token;
  }

  getUser(): UserProfile | null {
    return this.user;
  }

  isAuthenticated(): boolean {
    return !!this.token;
  }

  clearAuth() {
    this.token = null;
    this.user = null;
    localStorage.removeItem(TOKEN_KEY);
  }
}

export const userAuthService = new UserAuthService();
