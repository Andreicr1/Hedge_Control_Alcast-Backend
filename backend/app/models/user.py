"""
User Model

Usuários do sistema com perfis de acesso
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy import Enum as SQLEnum

from app.database import Base


class UserRole(str, Enum):
    """User roles/profiles"""

    FINANCEIRO = "financeiro"  # Financial team - full access to MTM, settlements, reports
    COMPRAS = "compras"  # Purchasing team - access to contracts, RFQs
    VENDAS = "vendas"  # Sales team - access to client operations, quotes


class User(Base):
    """User model"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.COMPRAS)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"

    @property
    def permissions(self) -> dict:
        """
        Get user permissions based on role
        """
        base_permissions = {
            "can_view_dashboard": True,
            "can_view_contracts": False,
            "can_edit_contracts": False,
            "can_view_rfqs": False,
            "can_edit_rfqs": False,
            "can_view_mtm": False,
            "can_view_settlements": False,
            "can_view_reports": False,
            "can_manage_users": False,
        }

        if self.role == UserRole.FINANCEIRO:
            return {
                **base_permissions,
                "can_view_contracts": True,
                "can_view_rfqs": True,
                "can_view_mtm": True,
                "can_view_settlements": True,
                "can_view_reports": True,
            }
        elif self.role == UserRole.COMPRAS:
            return {
                **base_permissions,
                "can_view_contracts": True,
                "can_edit_contracts": True,
                "can_view_rfqs": True,
                "can_edit_rfqs": True,
            }
        elif self.role == UserRole.VENDAS:
            return {
                **base_permissions,
                "can_view_contracts": True,
                "can_view_rfqs": True,
                "can_edit_rfqs": True,
            }

        if self.is_superuser:
            return {k: True for k in base_permissions.keys()}

        return base_permissions
