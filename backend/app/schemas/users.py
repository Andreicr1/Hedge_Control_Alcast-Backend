from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.domain import RoleName


class RoleRead(BaseModel):
    id: int
    name: RoleName
    description: Optional[str]

    class Config:
        orm_mode = True


class UserCreate(BaseModel):
    email: str  # Changed from EmailStr - .local domain not always valid
    name: str
    password: str
    role: RoleName = RoleName.compras


class UserRead(BaseModel):
    id: int
    email: str  # Changed from EmailStr - .local domain not always valid
    name: str
    role: Optional[RoleRead]
    active: bool
    created_at: datetime

    class Config:
        orm_mode = True
