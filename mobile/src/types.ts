export type User = {
  id: string;
  email: string;
  phone?: string | null;
  username?: string | null;
  avatar_url?: string | null;
  phone_verified_at?: string | null;
  last_login_at?: string | null;
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
};

export type SmsSendCodeResponse = {
  sent: boolean;
  purpose?: string;
  expire_seconds: number;
  retry_after_seconds: number;
  debug_code?: string | null;
};

export type FeishuStartLoginResponse = {
  session_id: string;
  state: string;
  authorize_url: string;
  expires_at: string;
};

export type FeishuSessionStatusResponse = {
  status: 'PENDING' | 'SUCCESS' | 'FAILED' | string;
  expires_at: string;
  completed_at?: string | null;
  error_message?: string | null;
  token?: AuthResponse | null;
};

export type SyncPlatformResult = {
  platform: string;
  status: string;
  items_count: number;
  error_code?: string | null;
  error_message?: string | null;
  alert_sent: boolean;
};

export type SyncRun = {
  id: string;
  user_id: string;
  trigger_source: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  added_count: number;
  updated_count: number;
  removed_count: number;
  error_summary?: string | null;
  platform_results: SyncPlatformResult[];
};

export type Bookmark = {
  id: string;
  platform: string;
  platform_item_id: string;
  title: string;
  url: string;
  cover_url?: string | null;
  content_updated_at?: string | null;
  first_collected_at: string;
  last_collected_at: string;
  removed_at?: string | null;
  category_id?: string | null;
  category_name?: string | null;
  category_confidence?: number | null;
  category_source: string;
};

export type Category = {
  id: string;
  name: string;
  source: string;
  created_at: string;
};
