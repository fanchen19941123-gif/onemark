# OneMark Mobile (Expo)

当前版本是可联通后端的移动端壳子，包含新版展示：

1. `首页` 双列瀑布流（封面 + 标题 + 平台 + 分类 + 时间）
   - 点击卡片会先确认，再跳转原始链接
   - 长按卡片可手动调整分类
2. `搜索`（后端自然语言搜索，支持“健身类的视频”“抖音里的健身视频”等）
   - 支持平台筛选（全部/抖音/小红书/B站）
   - 提供常用搜索建议
3. `同步`（手动触发 + 最近同步状态 + 任务记录）
4. `我`（用户信息 + 统计 + 退出）
5. 全页面支持下拉刷新，操作成功有绿色提示条

## 1. 启动后端

```bash
cd /Users/bytedance/Desktop/收藏夹管理助手/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 2. 配置 API 地址

默认读取：

- `EXPO_PUBLIC_API_BASE_URL`
- 未设置时默认 `http://127.0.0.1:8000`

### 模拟器

一般可用默认值。

### 真机

需要指向你电脑的局域网地址，例如：

```bash
export EXPO_PUBLIC_API_BASE_URL=http://192.168.1.20:8000
```

## 3. 启动移动端

```bash
cd /Users/bytedance/Desktop/收藏夹管理助手/mobile
npm install
npm run start -- --clear
```

## 4. 真机使用

1. iOS 用相机扫终端二维码打开 Expo。
2. 如果打开后卡在 `Opening project...`：
   - 手机和电脑必须在同一局域网
   - 关闭并重开 Expo Go 后重扫二维码
   - 终端重新执行 `npm run start -- --clear`

## 5. 封面不显示排查

1. 先确认已更新后端并重启：
   - `backend/app/scrapers/douyin.py` 已包含 cover URL 修复
2. 在 App 内手动触发一次抖音同步
3. 同步成功后，首页点击 `刷新`

## 6. AI 分类与语义搜索配置

在后端 `.env` 配置 Kimi（Moonshot）后生效：

```bash
LLM_API_KEY=***
LLM_BASE_URL=https://api.moonshot.cn/v1
LLM_MODEL=kimi-coding/k2p5
```

说明：

1. 新增收藏在同步后会自动 AI 分类。
2. `同步` 页的 `AI 回填分类` 可给历史未分类数据补分类。
3. `搜索` 页输入自然语言会调用 `/v1/bookmarks/search`。

## 7. 当前限制

1. B站抓取后端目前还是占位状态。
2. 若同步返回 `LOGIN_REQUIRED`，请确保 Chrome 已登录且可访问对应收藏页。
