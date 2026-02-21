from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import httpx
from sqlalchemy import asc, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Bookmark, Category


@dataclass
class SearchIntent:
    keywords: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    category_hints: list[str] = field(default_factory=list)
    sort: str = "recent"


class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_bookmarks(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int = 50,
    ) -> list[tuple[Bookmark, Category | None]]:
        intent = await self._parse_intent(query_text)

        query = (
            select(Bookmark, Category)
            .outerjoin(Category, Bookmark.category_id == Category.id)
            .where(
                Bookmark.user_id == user_id,
                Bookmark.removed_at.is_(None),
            )
        )

        if intent.platforms:
            query = query.where(Bookmark.platform.in_(intent.platforms))

        keyword_clauses = []
        for keyword in intent.keywords:
            like = f"%{keyword}%"
            keyword_clauses.append(
                or_(
                    Bookmark.title.ilike(like),
                    Bookmark.url.ilike(like),
                    Bookmark.platform.ilike(like),
                    Category.name.ilike(like),
                )
            )

        category_clauses = []
        for hint in intent.category_hints:
            like = f"%{hint}%"
            category_clauses.append(Category.name.ilike(like))

        text_clause = or_(*keyword_clauses) if keyword_clauses else None
        category_clause = or_(*category_clauses) if category_clauses else None
        if text_clause is not None and category_clause is not None:
            query = query.where(or_(text_clause, category_clause))
        elif text_clause is not None:
            query = query.where(text_clause)
        elif category_clause is not None:
            query = query.where(category_clause)

        if intent.sort == "oldest":
            query = query.order_by(asc(Bookmark.first_collected_at))
        else:
            query = query.order_by(desc(Bookmark.first_collected_at))

        final_limit = max(1, min(limit, 200))
        candidates_limit = max(
            final_limit * 4,
            min(max(settings.semantic_search_candidates, 60), 300),
        )
        rows = await self.db.execute(query.limit(candidates_limit))
        candidates = rows.all()

        if not candidates and query_text.strip():
            # Fallback to recent items so LLM can still do broad semantic matching.
            fallback_query = (
                select(Bookmark, Category)
                .outerjoin(Category, Bookmark.category_id == Category.id)
                .where(
                    Bookmark.user_id == user_id,
                    Bookmark.removed_at.is_(None),
                )
            )
            if intent.platforms:
                fallback_query = fallback_query.where(Bookmark.platform.in_(intent.platforms))
            fallback_query = fallback_query.order_by(desc(Bookmark.first_collected_at)).limit(candidates_limit)
            fallback_rows = await self.db.execute(fallback_query)
            candidates = fallback_rows.all()

        ranked = await self._semantic_rerank(query_text=query_text, candidates=candidates, limit=final_limit)
        if ranked:
            return ranked[:final_limit]
        return candidates[:final_limit]

    async def _parse_intent(self, text: str) -> SearchIntent:
        normalized = (text or "").strip()
        if not normalized:
            return SearchIntent()

        llm_intent = await self._parse_intent_with_llm(normalized)
        if llm_intent is not None:
            llm_intent.platforms = _normalize_platforms(llm_intent.platforms)
            llm_intent.keywords = _normalize_keywords(llm_intent.keywords or _extract_keywords(normalized))
            llm_intent.category_hints = _merge_unique(
                llm_intent.category_hints,
                _infer_category_hints(normalized),
            )
            return llm_intent

        return SearchIntent(
            keywords=_normalize_keywords(_extract_keywords(normalized)),
            platforms=_infer_platforms(normalized),
            category_hints=_infer_category_hints(normalized),
            sort="oldest" if any(token in normalized for token in ["最早", "早一点", "旧"]) else "recent",
        )

    async def _parse_intent_with_llm(self, text: str) -> SearchIntent | None:
        if not settings.effective_llm_api_key:
            return None

        prompt = (
            "你是收藏搜索解析器。请把用户查询转换成 JSON。"
            '\n输出严格 JSON: {"keywords":[""],"platforms":["douyin|xiaohongshu|bilibili"],"category_hints":[""],"sort":"recent|oldest"}'
            "\n如果没有字段就给空数组，sort 默认 recent。不要解释。"
            f"\n用户查询：{text}"
        )
        headers = {
            "Authorization": f"Bearer {settings.effective_llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.effective_llm_model,
            "messages": [
                {"role": "system", "content": "你是严谨的搜索意图解析助手，只输出 JSON。"},
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
            sort = str(data.get("sort") or "recent").strip().lower()
            if sort not in {"recent", "oldest"}:
                sort = "recent"
            return SearchIntent(
                keywords=[str(x).strip() for x in (data.get("keywords") or []) if str(x).strip()],
                platforms=[str(x).strip() for x in (data.get("platforms") or []) if str(x).strip()],
                category_hints=[str(x).strip() for x in (data.get("category_hints") or []) if str(x).strip()],
                sort=sort,
            )
        except Exception:
            return None

    async def _semantic_rerank(
        self,
        *,
        query_text: str,
        candidates: list[tuple[Bookmark, Category | None]],
        limit: int,
    ) -> list[tuple[Bookmark, Category | None]]:
        if not query_text.strip():
            return candidates[:limit]
        if not candidates:
            return []
        if not settings.effective_llm_api_key:
            return candidates[:limit]

        candidate_payload = []
        row_map: dict[str, tuple[Bookmark, Category | None]] = {}
        for bookmark, category in candidates:
            row_map[bookmark.id] = (bookmark, category)
            candidate_payload.append(
                {
                    "id": bookmark.id,
                    "title": bookmark.title or "",
                    "platform": bookmark.platform,
                    "category": category.name if category else "",
                    "url_hint": (bookmark.url or "")[:100],
                }
            )

        prompt = (
            "你是收藏检索排序器。任务：根据用户查询，从候选列表中选最相关条目并排序。"
            "\n规则：优先语义匹配，不要只看关键词字面。不要臆造ID。"
            '\n输出严格JSON：{"results":[{"id":"候选id","score":0-1,"reason":"简短中文理由"}]}'
            f"\n最多返回 {max(5, min(limit * 2, 60))} 条。"
            f"\n用户查询：{query_text}"
            f"\n候选列表：{json.dumps(candidate_payload, ensure_ascii=False)}"
        )

        headers = {
            "Authorization": f"Bearer {settings.effective_llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.effective_llm_model,
            "messages": [
                {"role": "system", "content": "你是严谨的搜索重排助手，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }

        try:
            async with httpx.AsyncClient(timeout=28) as client:
                response = await client.post(
                    f"{settings.effective_llm_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = _safe_parse_json(content)
            if not data:
                return candidates[:limit]
            results = data.get("results") or []
            if not isinstance(results, list):
                return candidates[:limit]

            ordered_ids: list[str] = []
            for item in results:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "").strip()
                if item_id and item_id in row_map and item_id not in ordered_ids:
                    ordered_ids.append(item_id)

            if not ordered_ids:
                return candidates[:limit]

            reranked = [row_map[item_id] for item_id in ordered_ids]
            for bookmark, category in candidates:
                if bookmark.id not in ordered_ids:
                    reranked.append((bookmark, category))
            return reranked
        except Exception:
            return candidates[:limit]


def _extract_keywords(text: str) -> list[str]:
    tokens = re.split(r"[\s,，。.!！？;；/]+", text)
    result = [token.strip() for token in tokens if token.strip()]
    return result[:6]


def _normalize_keywords(tokens: list[str]) -> list[str]:
    normalized: list[str] = []
    for token in tokens:
        value = (token or "").strip()
        if not value:
            continue
        candidates = [value]
        simplified = value
        for stopper in ["类的视频", "类视频", "的视频", "视频", "内容", "相关", "一下", "帮我", "给我", "想看", "类"]:
            simplified = simplified.replace(stopper, "")
        simplified = simplified.strip()
        if simplified and simplified != value:
            candidates.append(simplified)
        for candidate in candidates:
            if len(candidate) < 2 and candidate.lower() not in {"ai", "dy", "xhs"}:
                continue
            if candidate not in normalized:
                normalized.append(candidate)
    return normalized[:8]


def _infer_platforms(text: str) -> list[str]:
    found = []
    mapping = {
        "douyin": ["抖音", "douyin", "dy"],
        "xiaohongshu": ["小红书", "xhs", "xiaohongshu", "红书"],
        "bilibili": ["b站", "bilibili", "哔哩"],
    }
    lower = text.lower()
    for platform, keywords in mapping.items():
        if any(keyword in lower for keyword in keywords):
            found.append(platform)
    return found


def _infer_category_hints(text: str) -> list[str]:
    mapping = {
        "健身": ["健身", "减脂", "训练", "跑步", "力量", "瑜伽", "增肌", "塑形"],
        "美食": ["美食", "做饭", "菜谱", "探店", "吃", "烘焙"],
        "旅行": ["旅行", "旅游", "攻略", "酒店", "景点", "citywalk"],
        "技术": ["技术", "代码", "编程", "开发", "后端", "前端", "ai"],
        "购物": ["购物", "种草", "好物", "开箱", "穿搭", "护肤", "彩妆"],
        "影视": ["电影", "电视剧", "综艺", "动漫", "纪录片"],
        "阅读": ["阅读", "书单", "读书", "文学", "写作"],
    }
    lower = text.lower()
    hints: list[str] = []
    for category, keywords in mapping.items():
        if any(keyword in lower for keyword in keywords):
            hints.append(category)
    return hints


def _merge_unique(primary: list[str], secondary: list[str]) -> list[str]:
    result: list[str] = []
    for item in [*primary, *secondary]:
        text = (item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _normalize_platforms(platforms: list[str]) -> list[str]:
    allowed = {"douyin", "xiaohongshu", "bilibili"}
    result = []
    for platform in platforms:
        key = platform.strip().lower()
        if key in allowed and key not in result:
            result.append(key)
    return result


def _safe_parse_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    if "```" in text:
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(text)
        except Exception:
            return None
    return None
