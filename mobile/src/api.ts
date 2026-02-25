import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  AuthResponse,
  Bookmark,
  Category,
  FeishuSessionStatusResponse,
  FeishuStartLoginResponse,
  SmsSendCodeResponse,
  SyncRun,
  User,
} from './types';

const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
const ACCESS_TOKEN_KEY = 'onemark_access_token';
const REFRESH_TOKEN_KEY = 'onemark_refresh_token';

export const apiBaseUrl = API_BASE_URL;

async function request<T>(
  path: string,
  options: RequestInit = {},
  useAuth = false,
): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  headers.set('Content-Type', 'application/json');

  if (useAuth) {
    const token = await AsyncStorage.getItem(ACCESS_TOKEN_KEY);
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const detail = await parseError(response);
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === 'string') return data.detail;
    return JSON.stringify(data);
  } catch {
    return response.statusText;
  }
}

export async function register(email: string, password: string): Promise<AuthResponse> {
  const data = await request<AuthResponse>('/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  await persistTokens(data);
  return data;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const data = await request<AuthResponse>('/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  await persistTokens(data);
  return data;
}

export async function sendSmsCode(phone: string): Promise<SmsSendCodeResponse> {
  return request<SmsSendCodeResponse>('/v1/auth/sms/send-code', {
    method: 'POST',
    body: JSON.stringify({ phone, purpose: 'register' }),
  });
}

export async function sendLoginSmsCode(phone: string): Promise<SmsSendCodeResponse> {
  return request<SmsSendCodeResponse>('/v1/auth/sms/send-code', {
    method: 'POST',
    body: JSON.stringify({ phone, purpose: 'login' }),
  });
}

export async function startFeishuLogin(): Promise<FeishuStartLoginResponse> {
  return request<FeishuStartLoginResponse>('/v1/auth/feishu/start', {
    method: 'POST',
  });
}

export async function pollFeishuLoginSession(sessionId: string): Promise<FeishuSessionStatusResponse> {
  return request<FeishuSessionStatusResponse>(`/v1/auth/feishu/session/${sessionId}`);
}

export async function completeFeishuLoginSession(sessionId: string): Promise<FeishuSessionStatusResponse> {
  const data = await pollFeishuLoginSession(sessionId);
  if (data.token) {
    await persistTokens(data.token);
  }
  return data;
}

export async function registerWithSms(
  phone: string,
  code: string,
  password: string,
  username?: string,
  avatar_url?: string,
): Promise<AuthResponse> {
  const data = await request<AuthResponse>('/v1/auth/sms/register', {
    method: 'POST',
    body: JSON.stringify({ phone, code, password, username, avatar_url }),
  });
  await persistTokens(data);
  return data;
}

export async function loginWithPhonePassword(phone: string, password: string): Promise<AuthResponse> {
  const data = await request<AuthResponse>('/v1/auth/phone/login', {
    method: 'POST',
    body: JSON.stringify({ phone, password }),
  });
  await persistTokens(data);
  return data;
}

export async function loginWithSms(phone: string, code: string): Promise<AuthResponse> {
  const data = await request<AuthResponse>('/v1/auth/sms/login', {
    method: 'POST',
    body: JSON.stringify({ phone, code }),
  });
  await persistTokens(data);
  return data;
}

export async function getMe(): Promise<User> {
  return request<User>('/v1/auth/me', {}, true);
}

export async function updateMe(payload: { username?: string | null; avatar_url?: string | null }): Promise<User> {
  return request<User>('/v1/auth/me', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }, true);
}

export async function logout(): Promise<void> {
  await AsyncStorage.multiRemove([ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY]);
}

export async function getSavedAccessToken(): Promise<string | null> {
  return AsyncStorage.getItem(ACCESS_TOKEN_KEY);
}

export async function triggerSync(platforms: string[]): Promise<SyncRun> {
  return request<SyncRun>(
    '/v1/sync/runs',
    {
      method: 'POST',
      body: JSON.stringify({ platforms }),
    },
    true,
  );
}

export async function listSyncRuns(): Promise<SyncRun[]> {
  return request<SyncRun[]>('/v1/sync/runs', {}, true);
}

export async function listBookmarks(): Promise<Bookmark[]> {
  return request<Bookmark[]>('/v1/bookmarks', {}, true);
}

export async function searchBookmarks(query: string, limit = 50): Promise<Bookmark[]> {
  const q = encodeURIComponent(query);
  return request<Bookmark[]>(`/v1/bookmarks/search?q=${q}&limit=${limit}`, {}, true);
}

export async function listCategories(): Promise<Category[]> {
  return request<Category[]>('/v1/categories', {}, true);
}

export async function reclassifyBookmarks(limit = 200): Promise<{ classified_count: number }> {
  return request<{ classified_count: number }>(`/v1/bookmarks/reclassify?limit=${limit}`, { method: 'POST' }, true);
}

export async function updateBookmarkCategory(
  bookmarkId: string,
  payload: { category_id?: string; category_name?: string; clear?: boolean },
): Promise<Bookmark> {
  return request<Bookmark>(`/v1/bookmarks/${bookmarkId}/category`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }, true);
}

async function persistTokens(data: AuthResponse): Promise<void> {
  await AsyncStorage.multiSet([
    [ACCESS_TOKEN_KEY, data.access_token],
    [REFRESH_TOKEN_KEY, data.refresh_token],
  ]);
}
