from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=255)
    full_name: str | None = Field(default=None, max_length=150)
    role: UserRole = UserRole.TECHNICIAN
    unit: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(extra="forbid")


class UserUpdate(BaseModel):
    """Payload for partial user updates (admin only)."""

    full_name: str | None = Field(default=None, max_length=150)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=255)
    unit: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(extra="forbid")


class UserRead(BaseModel):
    id: int
    username: str
    full_name: str | None = None
    role: UserRole
    is_active: bool = True
    unit: str | None = None

    model_config = ConfigDict(from_attributes=True)
