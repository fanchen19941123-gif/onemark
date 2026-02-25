from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PhonePasswordLoginRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class SendSmsCodeRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    purpose: str = Field(default="register", max_length=32)


class SendSmsCodeResponse(BaseModel):
    sent: bool = True
    purpose: str = "register"
    expire_seconds: int
    retry_after_seconds: int
    debug_code: Optional[str] = None


class SmsLoginRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    code: str = Field(min_length=4, max_length=8)


class SmsRegisterRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    code: str = Field(min_length=4, max_length=8)
    password: str = Field(min_length=8, max_length=128)
    username: Optional[str] = Field(default=None, min_length=1, max_length=40)
    avatar_url: Optional[str] = Field(default=None, max_length=512)


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = Field(default=None, min_length=1, max_length=40)
    avatar_url: Optional[str] = Field(default=None, max_length=512)


class FeishuStartLoginResponse(BaseModel):
    session_id: str
    state: str
    authorize_url: str
    expires_at: datetime


class FeishuSessionStatusResponse(BaseModel):
    status: str
    expires_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    token: Optional["TokenResponse"] = None


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    phone: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    phone_verified_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


FeishuSessionStatusResponse.model_rebuild()
