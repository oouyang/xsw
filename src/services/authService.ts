import { api } from 'src/boot/axios';
import { jwtDecode } from 'jwt-decode';

export interface AuthUser {
  email: string;
  auth_method: 'google' | 'password';
  picture?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

interface TokenPayload {
  sub: string;
  auth_method: string;
  exp: number;
  iat: number;
}

const TOKEN_STORAGE_KEY = 'xsw_admin_token';

class AuthService {
  private token: string | null = null;
  private user: AuthUser | null = null;

  constructor() {
    // Load token from localStorage on init
    this.loadToken();
  }

  private loadToken() {
    try {
      const stored = localStorage.getItem(TOKEN_STORAGE_KEY);
      if (stored) {
        const data = JSON.parse(stored);
        this.token = data.token;
        this.user = data.user;

        // Verify token hasn't expired
        if (this.token && this.isTokenExpired(this.token)) {
          this.clearAuth();
        }
      }
    } catch (e) {
      console.error('[AuthService] Failed to load auth token:', e);
      this.clearAuth();
    }
  }

  private saveToken(token: string, user: AuthUser) {
    this.token = token;
    this.user = user;
    localStorage.setItem(
      TOKEN_STORAGE_KEY,
      JSON.stringify({ token, user })
    );
  }

  private isTokenExpired(token: string): boolean {
    try {
      const decoded = jwtDecode<TokenPayload>(token);
      return decoded.exp * 1000 < Date.now();
    } catch {
      return true;
    }
  }

  async authenticateWithGoogle(idToken: string): Promise<AuthResponse> {
    const response = await api.post<AuthResponse>('/auth/google', {
      id_token: idToken,
    });
    this.saveToken(response.data.access_token, response.data.user);
    return response.data;
  }

  async authenticateWithPassword(
    email: string,
    password: string
  ): Promise<AuthResponse> {
    const response = await api.post<AuthResponse>('/auth/password', {
      email,
      password,
    });
    this.saveToken(response.data.access_token, response.data.user);
    return response.data;
  }

  async changePassword(
    currentPassword: string,
    newPassword: string
  ): Promise<void> {
    await api.post(
      '/auth/password/change',
      {
        current_password: currentPassword,
        new_password: newPassword,
      },
      {
        headers: this.getAuthHeaders(),
      }
    );
  }

  async verifyToken(): Promise<boolean> {
    if (!this.token) return false;

    try {
      await api.get('/auth/verify', {
        headers: this.getAuthHeaders(),
      });
      return true;
    } catch {
      this.clearAuth();
      return false;
    }
  }

  getAuthHeaders(): Record<string, string> {
    if (!this.token) return {};
    return { Authorization: `Bearer ${this.token}` };
  }

  clearAuth() {
    this.token = null;
    this.user = null;
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }

  isAuthenticated(): boolean {
    return !!this.token && !this.isTokenExpired(this.token);
  }

  getUser(): AuthUser | null {
    return this.user;
  }

  getToken(): string | null {
    return this.token;
  }
}

export const authService = new AuthService();
