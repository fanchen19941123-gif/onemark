from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Bookmark, Category


@dataclass
class CategoryDecision:
    category_name: str
    confidence: float


class AIClassifierService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def classify_new_bookmarks(self, user_id: str, bookmarks: list[Bookmark]) -> None:
        if not bookmarks:
            return

        categories = await self._load_categories(user_id)
        for bookmark in bookmarks:
            decision = await self._decide_category(bookmark.title, categories)
            category = await self._get_or_create_category(user_id, decision.category_name, categories)

            bookmark.category_id = category.id
            bookmark.category_confidence = round(decision.confidence, 4)
            bookmark.category_source = "ai"

        await self.db.flush()

    async def classify_uncategorized_bookmarks(self, user_id: str, limit: int = 200) -> int:
        rows = await self.db.execute(
            select(Bookmark).where(
                Bookmark.user_id == user_id,
                Bookmark.removed_at.is_(None),
                Bookmark.category_id.is_(None),
            ).limit(max(1, min(limit, 1000)))
        )
        bookmarks = rows.scalars().all()
        if not bookmarks:
            return 0
        await self.classify_new_bookmarks(user_id, bookmarks)
        return len(bookmarks)

    async def _load_categories(self, user_id: str) -> dict[str, Category]:
        rows = await self.db.execute(
            select(Category).where(
                Category.user_id == user_id,
                Category.source == "ai",
            )
        )
        categories = rows.scalars().all()
        return {category.name: category for category in categories}

    async def _get_or_create_category(
        self,
        user_id: str,
        category_name: str,
        cache: dict[str, Category],
    ) -> Category:
        if category_name in cache:
            return cache[category_name]

        category = Category(user_id=user_id, name=category_name, source="ai")
        self.db.add(category)
        await self.db.flush()
        cache[category_name] = category
        return category

    async def _decide_category(self, title: str, existing_categories: dict[str, Category]) -> CategoryDecision:
        existing_names = list(existing_categories.keys())

        # First try LLM for semantic routing to existing categories.
        llm_decision = await self._classify_with_llm(title, existing_names)
        if llm_decision:
            if llm_decision.category_name in existing_categories:
                return llm_decision

            # If LLM proposes a new label, still prefer an existing category if it's close.
            closest = self._closest_existing(llm_decision.category_name, existing_names)
            if closest and closest[1] >= 0.86:
                return CategoryDecision(category_name=closest[0], confidence=max(llm_decision.confidence, closest[1]))

            return llm_decision

        # Fallback keyword mapping.
        fallback_name = self._rule_based_category(title)
        if fallback_name in existing_categories:
            return CategoryDecision(category_name=fallback_name, confidence=0.76)

        closest = self._closest_existing(fallback_name, existing_names)
        if closest and closest[1] >= 0.82:
            return CategoryDecision(category_name=closest[0], confidence=closest[1])

        return CategoryDecision(category_name=fallback_name, confidence=0.65)

    async def _classify_with_llm(self, title: str, existing_names: list[str]) -> CategoryDecision | None:
        if not settings.effective_llm_api_key:
            return None

        prompt = (
            "你是收藏内容分类器。目标：优先复用已有分类；只有确实不匹配时才创建新分类。"
            "\n返回严格 JSON：{\"category\":\"分类名\",\"confidence\":0-1}，不要解释。"
            f"\n已有分类：{existing_names if existing_names else '[]'}"
            f"\n标题：{title}"
        )

        headers = {
            "Authorization": f"Bearer {settings.effective_llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.effective_llm_model,
            "messages": [
                {"role": "system", "content": "你是严谨的分类助手，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{settings.effective_llm_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = _safe_parse_json(content)
            if not data:
                return None

            category = str(data.get("category") or "").strip()
            confidence = float(data.get("confidence") or 0.5)
            if not category:
                return None
            return CategoryDecision(category_name=category, confidence=max(0.0, min(1.0, confidence)))
        except Exception:
            return None

    def _rule_based_category(self, title: str) -> str:
        text = title.lower()
        rules = {
            "美食": ["美食", "做饭", "菜谱", "餐厅", "吃", "探店", "食堂", "烘焙"],
            "旅行": ["旅行", "旅游", "攻略", "酒店", "机票", "citywalk", "自驾", "景点"],
            "技术": ["技术", "编程", "代码", "python", "ai", "后端", "前端", "开发"],
            "购物": ["购物", "开箱", "种草", "好物", "买", "穿搭", "护肤", "彩妆"],
            "健身": ["健身", "减脂", "训练", "跑步", "力量", "瑜伽", "增肌"],
            "影视": ["电影", "电视剧", "综艺", "动漫", "纪录片", "追剧"],
            "阅读": ["阅读", "书单", "读书", "文学", "写作", "笔记"],
        }
        for category, keywords in rules.items():
            if any(keyword in text for keyword in keywords):
                return category
        return "其他"

    def _closest_existing(self, name: str, existing_names: list[str]) -> tuple[str, float] | None:
        if not existing_names:
            return None
        scored = [
            (candidate, SequenceMatcher(a=name.lower(), b=candidate.lower()).ratio())
            for candidate in existing_names
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0]


def _safe_parse_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except Exception:
        pass

    # tolerate fenced json
    if "```" in text:
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(text)
        except Exception:
            return None

    return None
