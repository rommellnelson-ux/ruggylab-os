from pydantic import BaseModel, ConfigDict

from app.models import UserRole


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str | None = None
    role: UserRole = UserRole.TECHNICIAN


class UserRead(BaseModel):
    id: int
    username: str
    full_name: str | None = None
    role: UserRole

    model_config = ConfigDict(from_attributes=True)
