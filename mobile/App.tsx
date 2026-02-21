import { StatusBar } from 'expo-status-bar';
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Linking,
  Modal,
  Pressable,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import {
  apiBaseUrl,
  getSavedAccessToken,
  listBookmarks,
  listCategories,
  reclassifyBookmarks,
  searchBookmarks,
  updateBookmarkCategory,
  listSyncRuns,
  login,
  logout,
  register,
  triggerSync,
} from './src/api';
import { Bookmark, Category, SyncRun, User } from './src/types';

type TabKey = 'home' | 'search' | 'sync' | 'me';

type PlatformMeta = {
  name: string;
  badge: string;
  color: string;
};

const PLATFORM_OPTIONS = ['douyin', 'xiaohongshu', 'bilibili'];
const PLATFORM_META: Record<string, PlatformMeta> = {
  douyin: { name: '抖音', badge: 'DY', color: '#111111' },
  xiaohongshu: { name: '小红书', badge: 'XHS', color: '#FF2442' },
  bilibili: { name: 'B站', badge: 'BILI', color: '#2CA6E0' },
};

const TAB_ITEMS: Array<{ key: TabKey; label: string }> = [
  { key: 'home', label: '首页' },
  { key: 'search', label: '搜索' },
  { key: 'sync', label: '同步' },
  { key: 'me', label: '我' },
];
const SEARCH_SUGGESTIONS = ['健身类的视频', '抖音里的美食', '小红书 旅行', '最近收藏的技术内容'];

export default function App() {
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [email, setEmail] = useState('singleuser@onemark.com');
  const [password, setPassword] = useState('StrongPass123!');
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [authLoading, setAuthLoading] = useState(false);

  const [activeTab, setActiveTab] = useState<TabKey>('home');
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(['douyin']);
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [searchText, setSearchText] = useState('');

  const [syncLoading, setSyncLoading] = useState(false);
  const [runsLoading, setRunsLoading] = useState(false);
  const [bookmarksLoading, setBookmarksLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [reclassifyLoading, setReclassifyLoading] = useState(false);
  const [categorySaving, setCategorySaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [latestSyncRun, setLatestSyncRun] = useState<SyncRun | null>(null);
  const [syncRuns, setSyncRuns] = useState<SyncRun[]>([]);
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [searchResultItems, setSearchResultItems] = useState<Bookmark[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [searchPlatform, setSearchPlatform] = useState<string>('all');

  const [coverRatios, setCoverRatios] = useState<Record<string, number>>({});
  const [detailItem, setDetailItem] = useState<Bookmark | null>(null);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string>('');
  const [newCategoryName, setNewCategoryName] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const token = await getSavedAccessToken();
        if (token) {
          setAuthed(true);
          await refreshAll();
        }
      } catch (e) {
        setError(getErrMessage(e));
      } finally {
        setReady(true);
      }
    })();
  }, []);

  useEffect(() => {
    const query = searchText.trim();
    if (!query) {
      setSearchResultItems(null);
      setSearchLoading(false);
      return;
    }

    let cancelled = false;
    const timer = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const rows = await searchBookmarks(query, 80);
        if (!cancelled) {
          setSearchResultItems(rows);
        }
      } catch (e) {
        if (!cancelled) {
          setError(getErrMessage(e));
        }
      } finally {
        if (!cancelled) {
          setSearchLoading(false);
        }
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [searchText]);

  useEffect(() => {
    if (!detailItem) {
      setSelectedCategoryId('');
      setNewCategoryName('');
      return;
    }
    setSelectedCategoryId(detailItem.category_id ?? '');
    setNewCategoryName('');
  }, [detailItem]);

  const categoryMap = useMemo(() => {
    const map = new Map<string, string>();
    categories.forEach((category) => {
      map.set(category.id, category.name);
    });
    return map;
  }, [categories]);

  const categoryOptions = useMemo(() => {
    return [{ id: 'all', name: '全部' }, ...categories.map((item) => ({ id: item.id, name: item.name }))];
  }, [categories]);

  const homeItems = useMemo(() => {
    if (activeCategory === 'all') return bookmarks;
    return bookmarks.filter((item) => item.category_id === activeCategory);
  }, [bookmarks, activeCategory]);

  const searchItems = useMemo(() => {
    const query = searchText.trim();
    const base = query ? (searchResultItems ?? []) : bookmarks;
    if (searchPlatform === 'all') return base;
    return base.filter((item) => item.platform === searchPlatform);
  }, [bookmarks, searchPlatform, searchResultItems, searchText]);

  const homeColumns = useMemo(
    () => splitIntoMasonry(homeItems, (item) => estimateCardHeight(item, coverRatios[item.id])),
    [homeItems, coverRatios],
  );

  const searchColumns = useMemo(
    () => splitIntoMasonry(searchItems, (item) => estimateCardHeight(item, coverRatios[item.id])),
    [searchItems, coverRatios],
  );

  const stats = useMemo(() => {
    const run = latestSyncRun ?? syncRuns[0] ?? null;
    return {
      bookmarkCount: bookmarks.length,
      categoryCount: categories.length,
      lastSyncAt: run?.finished_at ?? run?.started_at ?? null,
    };
  }, [bookmarks.length, categories.length, latestSyncRun, syncRuns]);

  async function handleAuth() {
    setAuthLoading(true);
    setError(null);
    setNotice(null);
    try {
      const data =
        mode === 'register'
          ? await register(email.trim(), password)
          : await login(email.trim(), password);
      setUser(data.user);
      setAuthed(true);
      await refreshAll();
      setNotice('登录成功');
    } catch (e) {
      setError(getErrMessage(e));
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleLogout() {
    await logout();
    setAuthed(false);
    setUser(null);
    setLatestSyncRun(null);
    setSyncRuns([]);
    setBookmarks([]);
    setSearchResultItems(null);
    setCategories([]);
    setCoverRatios({});
    setDetailItem(null);
    setError(null);
    setNotice(null);
  }

  async function refreshAll() {
    await Promise.all([loadRuns(), loadBookmarksAndCategories()]);
  }

  async function loadRuns() {
    setRunsLoading(true);
    setError(null);
    try {
      const runs = await listSyncRuns();
      setSyncRuns(runs);
      setLatestSyncRun(runs[0] ?? null);
    } catch (e) {
      setError(getErrMessage(e));
    } finally {
      setRunsLoading(false);
    }
  }

  async function loadBookmarksAndCategories() {
    setBookmarksLoading(true);
    setError(null);
    try {
      const [bookmarkRows, categoryRows] = await Promise.all([listBookmarks(), listCategories()]);
      setBookmarks(bookmarkRows);
      setCategories(categoryRows);
    } catch (e) {
      setError(getErrMessage(e));
    } finally {
      setBookmarksLoading(false);
    }
  }

  async function handleSyncNow() {
    setSyncLoading(true);
    setError(null);
    setNotice(null);
    try {
      const run = await triggerSync(selectedPlatforms);
      setLatestSyncRun(run);
      await refreshAll();
      setNotice(`同步完成：${run.status}`);
    } catch (e) {
      setError(getErrMessage(e));
    } finally {
      setSyncLoading(false);
    }
  }

  async function handleReclassify() {
    setReclassifyLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await reclassifyBookmarks(500);
      await loadBookmarksAndCategories();
      setNotice(`AI 分类完成：${result.classified_count} 条`);
    } catch (e) {
      setError(getErrMessage(e));
    } finally {
      setReclassifyLoading(false);
    }
  }

  function mergeUpdatedBookmark(updated: Bookmark) {
    setBookmarks((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    setSearchResultItems((prev) => (prev ? prev.map((item) => (item.id === updated.id ? updated : item)) : prev));
    setDetailItem((prev) => (prev?.id === updated.id ? updated : prev));
  }

  async function handleSaveCategory() {
    if (!detailItem) return;
    const categoryName = newCategoryName.trim();
    if (!categoryName && !selectedCategoryId) {
      setError('请选择分类或输入新分类名。');
      return;
    }

    setCategorySaving(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await updateBookmarkCategory(detailItem.id, categoryName
        ? { category_name: categoryName }
        : { category_id: selectedCategoryId });
      mergeUpdatedBookmark(updated);
      if (categoryName) {
        await loadBookmarksAndCategories();
      }
      setNotice('分类已更新');
      setDetailItem(null);
    } catch (e) {
      setError(getErrMessage(e));
    } finally {
      setCategorySaving(false);
    }
  }

  async function handleClearCategory() {
    if (!detailItem) return;
    setCategorySaving(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await updateBookmarkCategory(detailItem.id, { clear: true });
      mergeUpdatedBookmark(updated);
      setNotice('已清空分类');
      setDetailItem(null);
    } catch (e) {
      setError(getErrMessage(e));
    } finally {
      setCategorySaving(false);
    }
  }

  async function openOrigin(item: Bookmark) {
    try {
      await Linking.openURL(item.url);
    } catch {
      setError('无法打开原链接，请检查系统权限。');
    }
  }

  function confirmOpenOrigin(item: Bookmark) {
    Alert.alert(
      '打开原链接',
      '将跳转到平台原始页面，是否继续？',
      [
        { text: '取消', style: 'cancel' },
        { text: '打开', onPress: () => void openOrigin(item) },
      ],
      { cancelable: true },
    );
  }

  async function handlePullRefresh() {
    if (refreshing) return;
    setRefreshing(true);
    setError(null);
    try {
      await refreshAll();
      setNotice('已刷新最新数据');
    } catch (e) {
      setError(getErrMessage(e));
    } finally {
      setRefreshing(false);
    }
  }

  function togglePlatform(platform: string) {
    setSelectedPlatforms((prev) => {
      if (prev.includes(platform)) {
        return prev.filter((item) => item !== platform);
      }
      return [...prev, platform];
    });
  }

  function handleImageLoaded(bookmarkId: string, width?: number, height?: number) {
    if (!width || !height || !Number.isFinite(width) || !Number.isFinite(height)) {
      return;
    }
    const ratio = clamp(width / height, 0.55, 1.25);
    setCoverRatios((prev) => {
      if (prev[bookmarkId] && Math.abs(prev[bookmarkId] - ratio) < 0.01) {
        return prev;
      }
      return { ...prev, [bookmarkId]: ratio };
    });
  }

  function renderMasonry(items: [Bookmark[], Bookmark[]], emptyText: string) {
    if (bookmarksLoading) {
      return (
        <View style={styles.loadingWrap}>
          <ActivityIndicator size="small" color="#FF2442" />
          <Text style={styles.metaText}>加载中...</Text>
        </View>
      );
    }

    if (items[0].length === 0 && items[1].length === 0) {
      return <Text style={styles.emptyText}>{emptyText}</Text>;
    }

    return (
      <View style={styles.masonryRow}>
        <View style={styles.column}>{items[0].map((item) => renderCard(item))}</View>
        <View style={styles.column}>{items[1].map((item) => renderCard(item))}</View>
      </View>
    );
  }

  function renderCard(item: Bookmark) {
    const ratio = coverRatios[item.id] ?? guessAspectRatio(item);
    const categoryName = item.category_name ?? categoryMap.get(item.category_id ?? '') ?? '待分类';
    const platformMeta = getPlatformMeta(item.platform);

    return (
      <Pressable
        key={item.id}
        style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
        onPress={() => confirmOpenOrigin(item)}
        onLongPress={() => setDetailItem(item)}
        delayLongPress={220}
      >
        {item.cover_url ? (
          <Image
            source={{ uri: item.cover_url }}
            style={[styles.coverImage, { aspectRatio: ratio }]}
            onLoad={(event) => {
              handleImageLoaded(item.id, event.nativeEvent.source?.width, event.nativeEvent.source?.height);
            }}
          />
        ) : (
          <View style={[styles.coverPlaceholder, { aspectRatio: ratio }]}>
            <Text style={styles.coverPlaceholderText}>{platformMeta.badge}</Text>
          </View>
        )}

        <View style={styles.cardBody}>
          <Text numberOfLines={2} style={styles.cardTitle}>
            {item.title}
          </Text>
          <View style={styles.cardMetaRow}>
            <View style={[styles.platformBadge, { backgroundColor: platformMeta.color }]}>
              <Text style={styles.platformBadgeText}>{platformMeta.badge}</Text>
            </View>
            <Text style={styles.cardMetaText}>{platformMeta.name}</Text>
            <Text style={styles.cardDot}>·</Text>
            <Text style={styles.cardMetaText}>{categoryName}</Text>
          </View>
          <Text style={styles.cardTimeText}>{formatDate(item.first_collected_at)}</Text>
        </View>
      </Pressable>
    );
  }

  if (!ready) {
    return (
      <SafeAreaView style={styles.centered}>
        <StatusBar style="dark" />
        <ActivityIndicator size="large" color="#FF2442" />
      </SafeAreaView>
    );
  }

  if (!authed) {
    return (
      <SafeAreaView style={styles.authContainer}>
        <StatusBar style="dark" />
        <View style={styles.authCard}>
          <Text style={styles.brandTitle}>OneMark</Text>
          <Text style={styles.brandSub}>跨平台收藏，一屏沉浸浏览</Text>
          <Text style={styles.apiText}>API: {apiBaseUrl}</Text>

          <View style={styles.authModeRow}>
            <SegmentButton
              active={mode === 'login'}
              label="登录"
              onPress={() => setMode('login')}
            />
            <SegmentButton
              active={mode === 'register'}
              label="注册"
              onPress={() => setMode('register')}
            />
          </View>

          <TextInput
            autoCapitalize="none"
            keyboardType="email-address"
            placeholder="邮箱"
            placeholderTextColor="#7F7F87"
            style={styles.input}
            value={email}
            onChangeText={setEmail}
          />
          <TextInput
            secureTextEntry
            placeholder="密码"
            placeholderTextColor="#7F7F87"
            style={styles.input}
            value={password}
            onChangeText={setPassword}
          />

          <Pressable style={styles.primaryButton} onPress={handleAuth} disabled={authLoading}>
            <Text style={styles.primaryButtonText}>{authLoading ? '处理中...' : mode === 'login' ? '登录' : '注册并登录'}</Text>
          </Pressable>

          {error ? <Text style={styles.errorText}>{error}</Text> : null}
          <Text style={styles.tipText}>真机调试请把 EXPO_PUBLIC_API_BASE_URL 设为电脑局域网地址。</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.shell}>
      <StatusBar style="dark" />

      <View style={styles.topBar}>
        <View>
          <Text style={styles.topTitle}>一藏 OneMark</Text>
          <Text style={styles.topSub}>{user?.email ?? email}</Text>
        </View>
        <Pressable style={styles.refreshButton} onPress={refreshAll}>
          <Text style={styles.refreshButtonText}>刷新</Text>
        </Pressable>
      </View>

      <View style={styles.screenWrap}>
        {activeTab === 'home' ? (
          <ScrollView
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handlePullRefresh} tintColor="#FF2442" />}
          >
            <Text style={styles.sectionTitle}>发现</Text>
            <Text style={styles.metaText}>点击卡片直达原链接，长按可调整分类。</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsRow}>
              {categoryOptions.map((item) => {
                const active = activeCategory === item.id;
                return (
                  <Pressable
                    key={item.id}
                    onPress={() => setActiveCategory(item.id)}
                    style={[styles.filterChip, active && styles.filterChipActive]}
                  >
                    <Text style={[styles.filterChipText, active && styles.filterChipTextActive]}>{item.name}</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
            {renderMasonry(homeColumns, '暂无收藏，先去同步拉取内容。')}
          </ScrollView>
        ) : null}

        {activeTab === 'search' ? (
          <ScrollView
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handlePullRefresh} tintColor="#FF2442" />}
          >
            <Text style={styles.sectionTitle}>搜索</Text>
            <TextInput
              value={searchText}
              onChangeText={setSearchText}
              placeholder="自然语言搜索：如 抖音里的健身视频"
              placeholderTextColor="#7F7F87"
              style={styles.searchInput}
            />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsRow}>
              {[
                { key: 'all', label: '全部' },
                { key: 'douyin', label: '抖音' },
                { key: 'xiaohongshu', label: '小红书' },
                { key: 'bilibili', label: 'B站' },
              ].map((item) => {
                const active = searchPlatform === item.key;
                return (
                  <Pressable
                    key={item.key}
                    onPress={() => setSearchPlatform(item.key)}
                    style={[styles.filterChip, active && styles.filterChipActive]}
                  >
                    <Text style={[styles.filterChipText, active && styles.filterChipTextActive]}>{item.label}</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
            {!searchText.trim() ? (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsRow}>
                {SEARCH_SUGGESTIONS.map((item) => (
                  <Pressable key={item} onPress={() => setSearchText(item)} style={styles.searchSuggestionChip}>
                    <Text style={styles.searchSuggestionText}>{item}</Text>
                  </Pressable>
                ))}
              </ScrollView>
            ) : null}
            {searchLoading ? <ActivityIndicator size="small" color="#FF2442" /> : null}
            <Text style={styles.metaText}>结果 {searchItems.length} 条</Text>
            {renderMasonry(searchColumns, '没有匹配内容，换个关键词试试。')}
          </ScrollView>
        ) : null}

        {activeTab === 'sync' ? (
          <ScrollView
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handlePullRefresh} tintColor="#FF2442" />}
          >
            <Text style={styles.sectionTitle}>同步管理</Text>
            <Text style={styles.metaText}>选择平台后立即触发抓取。</Text>

            <View style={styles.chipsWrap}>
              {PLATFORM_OPTIONS.map((platform) => {
                const active = selectedPlatforms.includes(platform);
                const meta = getPlatformMeta(platform);
                return (
                  <Pressable
                    key={platform}
                    onPress={() => togglePlatform(platform)}
                    style={[styles.platformChip, active && styles.platformChipActive]}
                  >
                    <Text style={[styles.platformChipText, active && styles.platformChipTextActive]}>{meta.name}</Text>
                  </Pressable>
                );
              })}
            </View>

            <Pressable
              style={[styles.primaryButton, selectedPlatforms.length === 0 && styles.buttonDisabled]}
              onPress={handleSyncNow}
              disabled={syncLoading || selectedPlatforms.length === 0}
            >
              <Text style={styles.primaryButtonText}>{syncLoading ? '同步中...' : '立即同步'}</Text>
            </Pressable>
            <Pressable
              style={[styles.secondaryButton, reclassifyLoading && styles.buttonDisabled]}
              onPress={handleReclassify}
              disabled={reclassifyLoading}
            >
              <Text style={styles.secondaryButtonText}>
                {reclassifyLoading ? 'AI 分类中...' : 'AI 回填分类'}
              </Text>
            </Pressable>

            {latestSyncRun ? (
              <View style={styles.syncCard}>
                <Text style={styles.syncCardTitle}>最近同步</Text>
                <Text style={styles.syncCardText}>状态: {latestSyncRun.status}</Text>
                <Text style={styles.syncCardText}>
                  新增/更新/删除: {latestSyncRun.added_count}/{latestSyncRun.updated_count}/{latestSyncRun.removed_count}
                </Text>
                <Text style={styles.syncCardText}>时间: {formatDate(latestSyncRun.finished_at ?? latestSyncRun.started_at)}</Text>

                {latestSyncRun.platform_results.map((result) => (
                  <View key={`${latestSyncRun.id}_${result.platform}`} style={styles.platformResultRow}>
                    <Text style={styles.platformResultText}>
                      {getPlatformMeta(result.platform).name}: {result.status} ({result.items_count})
                    </Text>
                    {result.error_message ? <Text style={styles.errorText}>{result.error_message}</Text> : null}
                  </View>
                ))}
              </View>
            ) : null}

            <Text style={styles.sectionSubTitle}>最近任务</Text>
            {runsLoading ? <ActivityIndicator size="small" color="#FF2442" /> : null}
            {syncRuns.slice(0, 6).map((run) => (
              <View key={run.id} style={styles.runCard}>
                <Text style={styles.runCardTitle}>{run.status}</Text>
                <Text style={styles.runCardText}>触发: {run.trigger_source}</Text>
                <Text style={styles.runCardText}>开始: {formatDate(run.started_at)}</Text>
                <Text style={styles.runCardText}>结束: {formatDate(run.finished_at)}</Text>
              </View>
            ))}
            {syncRuns.length === 0 ? <Text style={styles.emptyText}>暂无任务记录。</Text> : null}
          </ScrollView>
        ) : null}

        {activeTab === 'me' ? (
          <ScrollView
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handlePullRefresh} tintColor="#FF2442" />}
          >
            <Text style={styles.sectionTitle}>我的</Text>
            <View style={styles.profileCard}>
              <View style={styles.avatarCircle}>
                <Text style={styles.avatarText}>ON</Text>
              </View>
              <View style={styles.profileTextWrap}>
                <Text style={styles.profileEmail}>{user?.email ?? email}</Text>
                <Text style={styles.metaText}>创建时间: {formatDate(user?.created_at)}</Text>
              </View>
            </View>

            <View style={styles.statsRow}>
              <View style={styles.statItem}>
                <Text style={styles.statNumber}>{stats.bookmarkCount}</Text>
                <Text style={styles.statLabel}>收藏</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={styles.statNumber}>{stats.categoryCount}</Text>
                <Text style={styles.statLabel}>分类</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={styles.statNumber}>{stats.lastSyncAt ? '已同步' : '未同步'}</Text>
                <Text style={styles.statLabel}>{formatDate(stats.lastSyncAt)}</Text>
              </View>
            </View>

            <View style={styles.meCard}>
              <Text style={styles.meCardTitle}>当前后端</Text>
              <Text style={styles.meCardText}>{apiBaseUrl}</Text>
            </View>

            <Pressable style={styles.logoutButton} onPress={handleLogout}>
              <Text style={styles.logoutButtonText}>退出登录</Text>
            </Pressable>
          </ScrollView>
        ) : null}
      </View>

      <View style={styles.tabBar}>
        {TAB_ITEMS.map((tab) => {
          const active = activeTab === tab.key;
          return (
            <Pressable key={tab.key} style={styles.tabButton} onPress={() => setActiveTab(tab.key)}>
              <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>{tab.label}</Text>
              {active ? <View style={styles.tabIndicator} /> : null}
            </Pressable>
          );
        })}
      </View>

      <Modal visible={!!detailItem} animationType="slide" transparent onRequestClose={() => setDetailItem(null)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>调整分类</Text>
              <Pressable onPress={() => setDetailItem(null)}>
                <Text style={styles.modalClose}>关闭</Text>
              </Pressable>
            </View>
            {detailItem ? (
              <ScrollView>
                <Text style={styles.modalBookmarkTitle}>{detailItem.title}</Text>
                <Text style={styles.modalMeta}>
                  当前分类: {detailItem.category_name ?? categoryMap.get(detailItem.category_id ?? '') ?? '待分类'}
                </Text>

                <Text style={styles.modalSectionTitle}>选择已有分类</Text>
                <View style={styles.modalChips}>
                  {categories.map((category) => {
                    const active = selectedCategoryId === category.id;
                    return (
                      <Pressable
                        key={category.id}
                        style={[styles.modalChip, active && styles.modalChipActive]}
                        onPress={() => {
                          setSelectedCategoryId(category.id);
                          setNewCategoryName('');
                        }}
                      >
                        <Text style={[styles.modalChipText, active && styles.modalChipTextActive]}>{category.name}</Text>
                      </Pressable>
                    );
                  })}
                </View>

                <Text style={styles.modalSectionTitle}>或新建分类</Text>
                <TextInput
                  value={newCategoryName}
                  onChangeText={setNewCategoryName}
                  placeholder="例如：健身"
                  placeholderTextColor="#7F7F87"
                  style={styles.modalInput}
                />

                <Pressable style={[styles.primaryButton, categorySaving && styles.buttonDisabled]} onPress={handleSaveCategory} disabled={categorySaving}>
                  <Text style={styles.primaryButtonText}>{categorySaving ? '保存中...' : '保存分类'}</Text>
                </Pressable>
                <Pressable style={[styles.secondaryButton, categorySaving && styles.buttonDisabled]} onPress={handleClearCategory} disabled={categorySaving}>
                  <Text style={styles.secondaryButtonText}>清空分类</Text>
                </Pressable>
              </ScrollView>
            ) : null}
          </View>
        </View>
      </Modal>

      {error ? (
        <Pressable style={styles.errorBanner} onPress={() => setError(null)}>
          <Text style={styles.errorBannerText}>{error}</Text>
        </Pressable>
      ) : null}
      {notice ? (
        <Pressable style={styles.noticeBanner} onPress={() => setNotice(null)}>
          <Text style={styles.noticeBannerText}>{notice}</Text>
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

function SegmentButton({
  active,
  label,
  onPress,
}: {
  active: boolean;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable style={[styles.segmentButton, active && styles.segmentButtonActive]} onPress={onPress}>
      <Text style={[styles.segmentButtonText, active && styles.segmentButtonTextActive]}>{label}</Text>
    </Pressable>
  );
}

function getPlatformMeta(platform: string): PlatformMeta {
  return PLATFORM_META[platform] ?? { name: platform, badge: platform.slice(0, 3).toUpperCase(), color: '#3D3D44' };
}

function splitIntoMasonry(items: Bookmark[], estimate: (item: Bookmark) => number): [Bookmark[], Bookmark[]] {
  const left: Bookmark[] = [];
  const right: Bookmark[] = [];
  let leftHeight = 0;
  let rightHeight = 0;

  for (const item of items) {
    const predicted = estimate(item);
    if (leftHeight <= rightHeight) {
      left.push(item);
      leftHeight += predicted;
    } else {
      right.push(item);
      rightHeight += predicted;
    }
  }

  return [left, right];
}

function estimateCardHeight(item: Bookmark, ratio?: number): number {
  const currentRatio = clamp(ratio ?? guessAspectRatio(item), 0.55, 1.25);
  const imageHeight = 168 / currentRatio;
  return imageHeight + 92;
}

function guessAspectRatio(item: Bookmark): number {
  const base = hash(`${item.id}-${item.platform_item_id}`);
  const ratios = [0.62, 0.72, 0.82, 1.0, 1.15];
  return ratios[base % ratios.length];
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function hash(value: string): number {
  let h = 0;
  for (let i = 0; i < value.length; i += 1) {
    h = (h * 31 + value.charCodeAt(i)) >>> 0;
  }
  return h;
}

function getErrMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Unknown error';
}

function formatDate(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

const styles = StyleSheet.create({
  shell: {
    flex: 1,
    backgroundColor: '#F6F7FB',
    paddingHorizontal: 12,
    paddingTop: 8,
  },
  centered: {
    flex: 1,
    backgroundColor: '#F6F7FB',
    alignItems: 'center',
    justifyContent: 'center',
  },
  authContainer: {
    flex: 1,
    backgroundColor: '#F6F7FB',
    paddingHorizontal: 16,
    justifyContent: 'center',
  },
  authCard: {
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#F0F1F5',
    backgroundColor: '#FFFFFF',
    padding: 20,
    shadowColor: '#111111',
    shadowOpacity: 0.08,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 3,
  },
  brandTitle: {
    color: '#1A1C24',
    fontSize: 30,
    fontWeight: '700',
    letterSpacing: 0.3,
  },
  brandSub: {
    color: '#6D7386',
    marginTop: 6,
    marginBottom: 6,
  },
  apiText: {
    color: '#8A91A4',
    fontSize: 12,
  },
  authModeRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 14,
    marginBottom: 10,
  },
  segmentButton: {
    flex: 1,
    borderRadius: 12,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
  },
  segmentButtonActive: {
    backgroundColor: '#FF2442',
    borderColor: '#FF2442',
  },
  segmentButtonText: {
    color: '#82889C',
    fontWeight: '600',
  },
  segmentButtonTextActive: {
    color: '#FFFFFF',
  },
  input: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    backgroundColor: '#FFFFFF',
    color: '#1D2330',
    paddingHorizontal: 12,
    paddingVertical: 12,
    marginBottom: 10,
  },
  primaryButton: {
    borderRadius: 12,
    backgroundColor: '#FF2442',
    alignItems: 'center',
    paddingVertical: 13,
    marginTop: 6,
    shadowColor: '#FF2442',
    shadowOpacity: 0.26,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontWeight: '700',
  },
  secondaryButton: {
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
    borderColor: '#ECEEF4',
    borderWidth: 1,
    alignItems: 'center',
    paddingVertical: 13,
    marginTop: 8,
  },
  secondaryButtonText: {
    color: '#5A6075',
    fontWeight: '600',
  },
  buttonDisabled: {
    opacity: 0.4,
  },
  tipText: {
    color: '#8A91A4',
    fontSize: 12,
    marginTop: 10,
    lineHeight: 17,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  topTitle: {
    color: '#161922',
    fontSize: 24,
    fontWeight: '700',
  },
  topSub: {
    color: '#7E8598',
    fontSize: 12,
  },
  refreshButton: {
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#F1D8DE',
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: '#FFFFFF',
  },
  refreshButtonText: {
    color: '#FF2442',
    fontWeight: '600',
  },
  screenWrap: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 100,
  },
  sectionTitle: {
    color: '#171B25',
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 10,
  },
  sectionSubTitle: {
    color: '#171B25',
    fontSize: 16,
    fontWeight: '700',
    marginTop: 12,
    marginBottom: 6,
  },
  chipsRow: {
    paddingBottom: 8,
    gap: 8,
  },
  filterChip: {
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    paddingHorizontal: 12,
    paddingVertical: 7,
    backgroundColor: '#FFFFFF',
  },
  filterChipActive: {
    backgroundColor: '#FF2442',
    borderColor: '#FF2442',
  },
  filterChipText: {
    color: '#606579',
    fontSize: 12,
    fontWeight: '600',
  },
  filterChipTextActive: {
    color: '#FFFFFF',
  },
  masonryRow: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'flex-start',
  },
  column: {
    flex: 1,
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#F0F1F5',
    marginBottom: 10,
    shadowColor: '#0E1018',
    shadowOpacity: 0.07,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  cardPressed: {
    opacity: 0.82,
    transform: [{ scale: 0.992 }],
  },
  coverImage: {
    width: '100%',
    backgroundColor: '#F1F2F7',
  },
  coverPlaceholder: {
    width: '100%',
    backgroundColor: '#F0F1F5',
    alignItems: 'center',
    justifyContent: 'center',
  },
  coverPlaceholderText: {
    color: '#969DB1',
    fontWeight: '700',
    fontSize: 16,
  },
  cardBody: {
    paddingHorizontal: 10,
    paddingTop: 9,
    paddingBottom: 10,
  },
  cardTitle: {
    color: '#1D2130',
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 18,
    minHeight: 36,
  },
  cardMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 8,
  },
  platformBadge: {
    borderRadius: 8,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginRight: 6,
  },
  platformBadgeText: {
    color: '#FFFFFF',
    fontSize: 9,
    fontWeight: '700',
  },
  cardMetaText: {
    color: '#72798E',
    fontSize: 11,
  },
  cardDot: {
    color: '#A2A8B9',
    marginHorizontal: 5,
    fontSize: 10,
  },
  cardTimeText: {
    color: '#8E94A8',
    fontSize: 11,
    marginTop: 6,
  },
  searchInput: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    backgroundColor: '#FFFFFF',
    color: '#1D2330',
    paddingHorizontal: 12,
    paddingVertical: 11,
    marginBottom: 8,
  },
  searchSuggestionChip: {
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#F1D8DE',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  searchSuggestionText: {
    color: '#FF5A76',
    fontSize: 12,
    fontWeight: '600',
  },
  metaText: {
    color: '#7B8397',
    fontSize: 12,
    marginBottom: 8,
  },
  emptyText: {
    color: '#969CAF',
    fontSize: 13,
    marginTop: 8,
  },
  loadingWrap: {
    alignItems: 'center',
    paddingVertical: 20,
  },
  chipsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginVertical: 10,
  },
  platformChip: {
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  platformChipActive: {
    borderColor: '#FF2442',
    backgroundColor: '#FFE9EE',
  },
  platformChipText: {
    color: '#666D82',
    fontWeight: '600',
    fontSize: 12,
  },
  platformChipTextActive: {
    color: '#FF2442',
  },
  syncCard: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    backgroundColor: '#FFFFFF',
    padding: 12,
    marginTop: 12,
  },
  syncCardTitle: {
    color: '#171B25',
    fontSize: 15,
    fontWeight: '700',
    marginBottom: 6,
  },
  syncCardText: {
    color: '#6D7488',
    fontSize: 12,
    marginBottom: 2,
  },
  platformResultRow: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#ECEEF4',
  },
  platformResultText: {
    color: '#3D4458',
    fontSize: 12,
    fontWeight: '600',
  },
  runCard: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    backgroundColor: '#FFFFFF',
    padding: 11,
    marginBottom: 8,
  },
  runCardTitle: {
    color: '#1D2230',
    fontSize: 13,
    fontWeight: '700',
    marginBottom: 4,
  },
  runCardText: {
    color: '#747B8F',
    fontSize: 12,
    marginBottom: 1,
  },
  profileCard: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    backgroundColor: '#FFFFFF',
    padding: 12,
    flexDirection: 'row',
    alignItems: 'center',
  },
  avatarCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#FF2442',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {
    color: '#FFFFFF',
    fontWeight: '700',
  },
  profileTextWrap: {
    marginLeft: 10,
  },
  profileEmail: {
    color: '#1D2230',
    fontWeight: '600',
    marginBottom: 3,
  },
  statsRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 10,
    marginBottom: 10,
  },
  statItem: {
    flex: 1,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    backgroundColor: '#FFFFFF',
    paddingVertical: 10,
    alignItems: 'center',
  },
  statNumber: {
    color: '#171B25',
    fontWeight: '700',
    fontSize: 14,
  },
  statLabel: {
    color: '#868DA0',
    fontSize: 11,
    marginTop: 3,
    textAlign: 'center',
  },
  meCard: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    backgroundColor: '#FFFFFF',
    padding: 12,
  },
  meCardTitle: {
    color: '#171B25',
    fontWeight: '700',
    marginBottom: 4,
  },
  meCardText: {
    color: '#767D92',
    fontSize: 12,
  },
  logoutButton: {
    borderRadius: 12,
    backgroundColor: '#FFF1F4',
    borderWidth: 1,
    borderColor: '#F7C8D2',
    alignItems: 'center',
    paddingVertical: 12,
    marginTop: 12,
  },
  logoutButtonText: {
    color: '#E63C5A',
    fontWeight: '700',
  },
  tabBar: {
    flexDirection: 'row',
    gap: 8,
    paddingTop: 8,
    paddingBottom: 10,
    borderTopWidth: 1,
    borderTopColor: '#ECEEF4',
    backgroundColor: '#FFFFFF',
  },
  tabButton: {
    flex: 1,
    borderRadius: 12,
    paddingVertical: 9,
    alignItems: 'center',
    backgroundColor: 'transparent',
  },
  tabLabel: {
    color: '#8A90A3',
    fontWeight: '600',
  },
  tabLabelActive: {
    color: '#FF2442',
  },
  tabIndicator: {
    marginTop: 4,
    width: 14,
    height: 3,
    borderRadius: 2,
    backgroundColor: '#FF2442',
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.22)',
    justifyContent: 'flex-end',
  },
  modalCard: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '90%',
    paddingHorizontal: 14,
    paddingTop: 12,
    paddingBottom: 24,
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  modalTitle: {
    color: '#171B25',
    fontSize: 18,
    fontWeight: '700',
  },
  modalClose: {
    color: '#FF3B5D',
    fontWeight: '600',
  },
  modalCover: {
    width: '100%',
    borderRadius: 12,
    backgroundColor: '#202024',
    marginBottom: 10,
  },
  modalBookmarkTitle: {
    color: '#1E2432',
    fontSize: 17,
    fontWeight: '700',
    marginBottom: 8,
  },
  modalMeta: {
    color: '#6F768B',
    fontSize: 12,
    marginBottom: 4,
  },
  modalSectionTitle: {
    color: '#333A4E',
    fontSize: 12,
    fontWeight: '600',
    marginTop: 10,
    marginBottom: 6,
  },
  modalChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  modalChip: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#FFFFFF',
  },
  modalChipActive: {
    borderColor: '#FF2442',
    backgroundColor: '#FFE9EE',
  },
  modalChipText: {
    color: '#676E82',
    fontSize: 12,
    fontWeight: '600',
  },
  modalChipTextActive: {
    color: '#FF2442',
  },
  modalInput: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#ECEEF4',
    backgroundColor: '#FFFFFF',
    color: '#1D2330',
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 6,
  },
  errorText: {
    color: '#E64461',
    marginTop: 6,
    fontSize: 12,
  },
  errorBanner: {
    position: 'absolute',
    left: 14,
    right: 14,
    bottom: 72,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#F3C8D0',
    backgroundColor: '#FFF2F5',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  errorBannerText: {
    color: '#D43B57',
    fontSize: 12,
  },
  noticeBanner: {
    position: 'absolute',
    left: 14,
    right: 14,
    bottom: 126,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#C7E9D5',
    backgroundColor: '#F2FCF6',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  noticeBannerText: {
    color: '#2F7B50',
    fontSize: 12,
  },
});
