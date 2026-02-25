import hashlib
import html
import random
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import FeishuLoginSession, SmsLoginCode, User
from app.schemas.auth import (
    FeishuSessionStatusResponse,
    FeishuStartLoginResponse,
    LoginRequest,
    PhonePasswordLoginRequest,
    RefreshRequest,
    RegisterRequest,
    SendSmsCodeRequest,
    SendSmsCodeResponse,
    SmsRegisterRequest,
    SmsLoginRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["auth"])
PHONE_RE = re.compile(r"^1\d{10}$")
ALLOWED_SMS_PURPOSES = {"register", "login"}
FEISHU_AUTHORIZE_ENDPOINT = "https://open.feishu.cn/open-apis/authen/v1/index"
FEISHU_TENANT_TOKEN_ENDPOINT = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_ACCESS_TOKEN_ENDPOINT = "https://open.feishu.cn/open-apis/authen/v1/access_token"
FEISHU_USERINFO_ENDPOINT = "https://open.feishu.cn/open-apis/authen/v1/user_info"


@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    user = User(email=payload.email, password_hash=get_password_hash(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return _build_token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    now = datetime.now(timezone.utc)
    user.last_login_at = now
    await db.commit()
    await db.refresh(user)
    return _build_token_response(user)


@router.post("/phone/login", response_model=TokenResponse)
async def login_with_phone_password(
    payload: PhonePasswordLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    phone = _normalize_phone(payload.phone)
    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid phone or password")

    now = datetime.now(timezone.utc)
    user.last_login_at = now
    await db.commit()
    await db.refresh(user)
    return _build_token_response(user)


@router.post("/feishu/start", response_model=FeishuStartLoginResponse)
async def feishu_start_login(db: AsyncSession = Depends(get_db)) -> FeishuStartLoginResponse:
    _ensure_feishu_configured()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.feishu_session_expire_seconds)
    state = secrets.token_urlsafe(24)
    session = FeishuLoginSession(
        state=state,
        status="PENDING",
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    query = urlencode(
        {
            "app_id": settings.feishu_app_id,
            "redirect_uri": settings.feishu_redirect_uri,
            "scope": settings.feishu_oauth_scope,
            "state": state,
        }
    )
    authorize_url = f"{FEISHU_AUTHORIZE_ENDPOINT}?{query}"
    return FeishuStartLoginResponse(
        session_id=session.id,
        state=state,
        authorize_url=authorize_url,
        expires_at=_as_utc(session.expires_at),
    )


@router.get("/feishu/session/{session_id}", response_model=FeishuSessionStatusResponse)
async def feishu_login_session_status(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> FeishuSessionStatusResponse:
    row = await db.execute(select(FeishuLoginSession).where(FeishuLoginSession.id == session_id))
    session = row.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    now = datetime.now(timezone.utc)
    if _as_utc(session.expires_at) < now and session.status == "PENDING":
        session.status = "FAILED"
        session.error_message = "Login session expired"
        await db.commit()
        await db.refresh(session)

    if session.status == "SUCCESS":
        if session.consumed_at is not None:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Session already consumed")
        if not session.access_token or not session.refresh_token or not session.user_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Session token missing")
        user_row = await db.execute(select(User).where(User.id == session.user_id))
        user = user_row.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User not found")
        token = TokenResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            user=_to_user_response(user),
        )
        session.consumed_at = now
        await db.commit()
        await db.refresh(session)
        return FeishuSessionStatusResponse(
            status=session.status,
            expires_at=_as_utc(session.expires_at),
            completed_at=_as_utc(session.completed_at) if session.completed_at else None,
            token=token,
        )

    return FeishuSessionStatusResponse(
        status=session.status,
        expires_at=_as_utc(session.expires_at),
        completed_at=_as_utc(session.completed_at) if session.completed_at else None,
        error_message=session.error_message,
    )


@router.get("/feishu/callback")
async def feishu_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    safe_message = "登录完成，请回到 OneMark App。"

    if state is None:
        return _feishu_callback_html("参数缺失：state")

    row = await db.execute(select(FeishuLoginSession).where(FeishuLoginSession.state == state))
    session = row.scalar_one_or_none()
    if session is None:
        return _feishu_callback_html("登录会话不存在或已过期。")

    now = datetime.now(timezone.utc)
    if _as_utc(session.expires_at) < now:
        session.status = "FAILED"
        session.error_message = "Login session expired"
        session.completed_at = now
        await db.commit()
        return _feishu_callback_html("登录会话已过期，请返回 App 重试。")

    if error:
        session.status = "FAILED"
        session.error_message = f"{error}: {error_description or ''}".strip()
        session.completed_at = now
        await db.commit()
        return _feishu_callback_html("飞书授权失败，请返回 App 重试。")

    if not code:
        session.status = "FAILED"
        session.error_message = "Missing code"
        session.completed_at = now
        await db.commit()
        return _feishu_callback_html("缺少授权码，请返回 App 重试。")

    try:
        user = await _login_or_register_via_feishu(code=code, db=db)
        session.status = "SUCCESS"
        session.user_id = user.id
        session.access_token = create_access_token(user.id)
        session.refresh_token = create_refresh_token(user.id)
        session.error_message = None
        session.completed_at = now
    except Exception as exc:  # noqa: BLE001
        session.status = "FAILED"
        session.error_message = str(exc)
        session.completed_at = now
    await db.commit()
    return _feishu_callback_html(safe_message if session.status == "SUCCESS" else "飞书登录失败，请返回 App 重试。")


@router.post("/sms/send-code", response_model=SendSmsCodeResponse)
async def send_sms_code(
    payload: SendSmsCodeRequest,
    db: AsyncSession = Depends(get_db),
) -> SendSmsCodeResponse:
    phone = _normalize_phone(payload.phone)
    purpose = _normalize_sms_purpose(payload.purpose)
    now = datetime.now(timezone.utc)
    cooldown_from = now - timedelta(seconds=settings.sms_send_cooldown_seconds)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    daily_sent = await db.execute(
        select(func.count())
        .select_from(SmsLoginCode)
        .where(
            and_(
                SmsLoginCode.phone == phone,
                SmsLoginCode.purpose == purpose,
                SmsLoginCode.created_at >= day_start,
            )
        )
    )
    if (daily_sent.scalar_one() or 0) >= settings.sms_daily_send_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"SMS limit reached today ({settings.sms_daily_send_limit})",
        )

    latest = await db.execute(
        select(SmsLoginCode)
        .where(
            and_(
                SmsLoginCode.phone == phone,
                SmsLoginCode.purpose == purpose,
                SmsLoginCode.created_at >= cooldown_from,
            )
        )
        .order_by(SmsLoginCode.created_at.desc())
        .limit(1)
    )
    if latest.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {settings.sms_send_cooldown_seconds}s before requesting another code",
        )

    code = f"{random.randint(0, 999999):06d}"
    await db.execute(
        update(SmsLoginCode)
        .where(
            and_(
                SmsLoginCode.phone == phone,
                SmsLoginCode.purpose == purpose,
                SmsLoginCode.used_at.is_(None),
            )
        )
        .values(used_at=now)
    )

    code_row = SmsLoginCode(
        phone=phone,
        purpose=purpose,
        code_hash=_hash_code(phone, code),
        expires_at=now + timedelta(seconds=settings.sms_code_expire_seconds),
    )
    db.add(code_row)
    await db.commit()

    # Placeholder SMS sender for local MVP: only print code in backend logs.
    print(f"[SMS_DEBUG] phone={phone} purpose={purpose} code={code}")

    return SendSmsCodeResponse(
        sent=True,
        purpose=purpose,
        expire_seconds=settings.sms_code_expire_seconds,
        retry_after_seconds=settings.sms_send_cooldown_seconds,
        debug_code=code if settings.sms_debug_return_code else None,
    )


@router.post("/sms/register", response_model=TokenResponse)
async def register_with_sms(
    payload: SmsRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    phone = _normalize_phone(payload.phone)
    code = payload.code.strip()
    now = datetime.now(timezone.utc)

    existing = await db.execute(select(User).where(User.phone == phone))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone already registered")

    code_row = await _get_latest_sms_code(db, phone, purpose="register")
    await _validate_sms_code(db, code_row, phone, code, now)

    user = User(
        email=_build_synthetic_email(phone),
        phone=phone,
        display_name=_normalize_username(payload.username) or _default_username(phone),
        avatar_url=_normalize_avatar_url(payload.avatar_url),
        password_hash=get_password_hash(payload.password),
        phone_verified_at=now,
        last_login_at=now,
    )
    db.add(user)
    code_row.used_at = now
    await db.commit()
    await db.refresh(user)
    return _build_token_response(user)


@router.post("/sms/login", response_model=TokenResponse)
async def login_with_sms(
    payload: SmsLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    phone = _normalize_phone(payload.phone)
    code = payload.code.strip()
    now = datetime.now(timezone.utc)

    code_row = await _get_latest_sms_code(db, phone, purpose="login")
    await _validate_sms_code(db, code_row, phone, code, now)

    user_row = await db.execute(select(User).where(User.phone == phone))
    user = user_row.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone not registered")

    code_row.used_at = now
    user.phone_verified_at = user.phone_verified_at or now
    user.last_login_at = now
    await db.commit()
    await db.refresh(user)
    return _build_token_response(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        token_payload = decode_token(payload.refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if token_payload.get("type") != TokenType.REFRESH:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    now = datetime.now(timezone.utc)
    user.last_login_at = now
    await db.commit()
    await db.refresh(user)
    return _build_token_response(user)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _to_user_response(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    if "username" in payload.model_fields_set:
        current_user.display_name = _normalize_username(payload.username)
    if "avatar_url" in payload.model_fields_set:
        current_user.avatar_url = _normalize_avatar_url(payload.avatar_url)

    await db.commit()
    await db.refresh(current_user)
    return _to_user_response(current_user)



def _build_token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=_to_user_response(user),
    )


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
        username=user.display_name,
        avatar_url=user.avatar_url,
        phone_verified_at=user.phone_verified_at,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


def _normalize_phone(phone: str) -> str:
    normalized = re.sub(r"\D", "", (phone or "").strip())
    if not PHONE_RE.match(normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid phone number")
    return normalized


def _normalize_sms_purpose(purpose: str) -> str:
    normalized = (purpose or "").strip().lower()
    if normalized not in ALLOWED_SMS_PURPOSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sms purpose: {purpose}",
        )
    return normalized


def _normalize_username(username: Optional[str]) -> Optional[str]:
    if username is None:
        return None
    value = username.strip()
    if not value:
        return None
    if len(value) > 40:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username too long")
    return value


def _normalize_avatar_url(avatar_url: Optional[str]) -> Optional[str]:
    if avatar_url is None:
        return None
    value = avatar_url.strip()
    if not value:
        return None
    if len(value) > 512:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Avatar URL too long")
    return value


def _default_username(phone: str) -> str:
    return f"用户{phone[-4:]}"


def _build_synthetic_email(phone: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "", (phone or "").strip())
    if not normalized:
        normalized = secrets.token_hex(8)
    return f"u_{normalized[:32]}@phone.onemark.app"


def _hash_code(phone: str, code: str) -> str:
    payload = f"{phone}:{code}:{settings.secret_key}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _get_latest_sms_code(
    db: AsyncSession,
    phone: str,
    purpose: str,
) -> Optional[SmsLoginCode]:
    row = await db.execute(
        select(SmsLoginCode)
        .where(
            and_(
                SmsLoginCode.phone == phone,
                SmsLoginCode.purpose == purpose,
                SmsLoginCode.used_at.is_(None),
            )
        )
        .order_by(SmsLoginCode.created_at.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


async def _validate_sms_code(
    db: AsyncSession,
    code_row: Optional[SmsLoginCode],
    phone: str,
    input_code: str,
    now: datetime,
) -> None:
    if code_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code not found")

    if _as_utc(code_row.expires_at) < now:
        code_row.used_at = now
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code expired")

    if code_row.failed_attempts >= settings.sms_code_max_attempts:
        code_row.used_at = code_row.used_at or now
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Too many attempts, request a new code")

    if code_row.code_hash != _hash_code(phone, input_code):
        code_row.failed_attempts += 1
        code_row.last_attempt_at = now
        if code_row.failed_attempts >= settings.sms_code_max_attempts:
            code_row.used_at = now
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid code")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ensure_feishu_configured() -> None:
    if not settings.feishu_app_id or not settings.feishu_app_secret or not settings.feishu_redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feishu login not configured. Set FEISHU_APP_ID/FEISHU_APP_SECRET/FEISHU_REDIRECT_URI.",
        )


def _normalize_feishu_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("86") and len(digits) > 11:
        digits = digits[-11:]
    if PHONE_RE.match(digits):
        return digits
    return None


async def _login_or_register_via_feishu(code: str, db: AsyncSession) -> User:
    _ensure_feishu_configured()
    now = datetime.now(timezone.utc)
    tenant_access_token = await _fetch_feishu_tenant_access_token()
    auth_data = await _fetch_feishu_user_token(code=code, tenant_access_token=tenant_access_token)
    user_info = await _fetch_feishu_user_info(user_access_token=auth_data["user_access_token"])

    feishu_open_id = auth_data.get("open_id") or user_info.get("open_id")
    feishu_union_id = auth_data.get("union_id") or user_info.get("union_id")
    if not feishu_open_id and not feishu_union_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Feishu identity missing open_id/union_id")

    phone = _normalize_feishu_phone(user_info.get("mobile"))
    email = (user_info.get("email") or "").strip().lower() or None
    name = _normalize_username(user_info.get("name"))
    avatar_url = _normalize_avatar_url(user_info.get("avatar_url"))
    tenant_key = (auth_data.get("tenant_key") or "").strip() or None

    user = await _find_user_for_feishu(
        db=db,
        feishu_open_id=feishu_open_id,
        feishu_union_id=feishu_union_id,
        email=email,
        phone=phone,
    )
    if user is None:
        synthetic_email = email or _build_synthetic_email(phone or str(int(now.timestamp())))
        user = User(
            email=synthetic_email,
            phone=phone,
            display_name=name or _default_username(phone or str(int(now.timestamp()))),
            avatar_url=avatar_url,
            password_hash=get_password_hash(_random_password_seeded(f"{feishu_open_id}:{now.isoformat()}")),
            phone_verified_at=now if phone else None,
        )
        db.add(user)
        await db.flush()

    user.feishu_open_id = user.feishu_open_id or feishu_open_id
    user.feishu_union_id = user.feishu_union_id or feishu_union_id
    user.feishu_tenant_key = tenant_key or user.feishu_tenant_key
    if phone and not user.phone:
        user.phone = phone
        user.phone_verified_at = now
    if name and not user.display_name:
        user.display_name = name
    if avatar_url and not user.avatar_url:
        user.avatar_url = avatar_url
    user.last_login_at = now
    await db.flush()
    await db.refresh(user)
    return user


async def _find_user_for_feishu(
    db: AsyncSession,
    feishu_open_id: Optional[str],
    feishu_union_id: Optional[str],
    email: Optional[str],
    phone: Optional[str],
) -> Optional[User]:
    if feishu_open_id:
        row = await db.execute(select(User).where(User.feishu_open_id == feishu_open_id))
        user = row.scalar_one_or_none()
        if user:
            return user
    if feishu_union_id:
        row = await db.execute(select(User).where(User.feishu_union_id == feishu_union_id))
        user = row.scalar_one_or_none()
        if user:
            return user
    if phone:
        row = await db.execute(select(User).where(User.phone == phone))
        user = row.scalar_one_or_none()
        if user:
            return user
    if email:
        row = await db.execute(select(User).where(User.email == email))
        user = row.scalar_one_or_none()
        if user:
            return user
    return None


async def _fetch_feishu_tenant_access_token() -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            FEISHU_TENANT_TOKEN_ENDPOINT,
            json={
                "app_id": settings.feishu_app_id,
                "app_secret": settings.feishu_app_secret,
            },
        )
    data = response.json()
    if response.status_code >= 400 or data.get("code") not in (0, "0"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Feishu tenant token failed: {data}")
    token = data.get("tenant_access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Feishu tenant token missing")
    return token


async def _fetch_feishu_user_token(code: str, tenant_access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            FEISHU_ACCESS_TOKEN_ENDPOINT,
            headers={"Authorization": f"Bearer {tenant_access_token}"},
            json={"grant_type": "authorization_code", "code": code},
        )
    data = response.json()
    if response.status_code >= 400 or data.get("code") not in (0, "0"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Feishu access_token failed: {data}")
    payload = data.get("data") or {}
    if not payload.get("user_access_token"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Feishu user_access_token missing")
    return payload


async def _fetch_feishu_user_info(user_access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            FEISHU_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {user_access_token}"},
        )
    data = response.json()
    if response.status_code >= 400 or data.get("code") not in (0, "0"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Feishu user_info failed: {data}")
    payload = data.get("data") or {}
    return payload


def _random_password_seeded(seed: str) -> str:
    token = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"FS_{token[:24]}!"


def _feishu_callback_html(message: str) -> HTMLResponse:
    safe_message = html.escape(message)
    return HTMLResponse(
        content=(
            "<html><head><meta charset='utf-8' /><meta name='viewport' content='width=device-width,initial-scale=1' />"
            "<title>OneMark 飞书登录</title></head>"
            "<body style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
            "padding:28px;background:#0b0d12;color:#f5f7ff;'>"
            "<h2 style='margin-top:0'>OneMark</h2>"
            f"<p>{safe_message}</p>"
            "<p style='opacity:.7'>你可以关闭本页面并返回 App。</p>"
            "</body></html>"
        )
    )
