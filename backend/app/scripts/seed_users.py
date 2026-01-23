"""Seed Users Script

Creates/updates default dev users.
Run with: python -m app.scripts.seed_users
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.domain import Role, RoleName, User
from app.services.auth import hash_password


def _role_name_to_str(value) -> str:
    if isinstance(value, RoleName):
        return value.value
    return str(value)


def ensure_base_roles(db: Session):
    """Ensure base roles exist.

    Some migrations recreate the roles table without reseeding.
    This keeps local/dev environments bootable.
    """

    existing = {
        _role_name_to_str(name) for (name,) in db.query(Role.name).all() if name is not None
    }

    role_specs = [
        (RoleName.admin.value, "Perfil Administrador"),
        (RoleName.financeiro.value, "Perfil Financeiro (hedge/RFQ/MTM)"),
        (RoleName.comercial.value, "Perfil Comercial (Compras + Vendas)"),
        (RoleName.estoque.value, "Perfil de Estoque"),
    ]

    created_any = False
    for role_name, description in role_specs:
        if role_name in existing:
            continue
        db.execute(
            text(
                """
                INSERT INTO roles (name, description)
                VALUES (:name, :description)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"name": role_name, "description": description},
        )
        created_any = True

    if created_any:
        db.commit()


def get_role_id(db: Session, role_name: RoleName) -> int | None:
    return db.execute(
        text("SELECT id FROM roles WHERE name = :name"),
        {"name": role_name.value},
    ).scalar_one_or_none()


def create_default_users(db: Session):
    """Create or update default users for each role."""

    ensure_base_roles(db)

    # Get role IDs
    role_admin_id = get_role_id(db, RoleName.admin)
    role_financeiro_id = get_role_id(db, RoleName.financeiro)
    role_comercial_id = get_role_id(db, RoleName.comercial)

    if not all([role_admin_id, role_financeiro_id, role_comercial_id]):
        print("❌ Error: Required roles not found in database. Run migrations first!")
        return

    users_to_create = [
        {
            "email": "admin@alcast.dev",
            "name": "Administrador",
            "password": "123",  # Dev default
            "role_id": role_admin_id,
        },
        {
            "email": "admin@alcast.local",
            "name": "Administrador (alias local)",
            "password": "123",  # Dev default
            "role_id": role_admin_id,
        },
        {
            "email": "financeiro@alcast.dev",
            "name": "Financeiro",
            "password": "123",  # Dev default
            "role_id": role_financeiro_id,
        },
        {
            "email": "comercial@alcast.dev",
            "name": "Comercial",
            "password": "123",  # Dev default
            "role_id": role_comercial_id,
        },
        {
            "email": "compras@alcast.dev",
            "name": "Comercial (alias compras)",
            "password": "123",  # Dev default
            "role_id": role_comercial_id,
        },
        {
            "email": "vendas@alcast.dev",
            "name": "Comercial (alias vendas)",
            "password": "123",  # Dev default
            "role_id": role_comercial_id,
        },
    ]

    print("\nSeeding default users...")

    for user_data in users_to_create:
        # Hash password
        password = user_data.pop("password")
        hashed_password = hash_password(password)

        user = db.query(User).filter(User.email == user_data["email"]).first()
        if user is None:
            user = User(
                **user_data,
                hashed_password=hashed_password,
                active=True,
            )
            db.add(user)
            action = "Created"
        else:
            user.name = user_data["name"]
            user.role_id = user_data["role_id"]
            user.active = True
            user.hashed_password = hashed_password
            db.add(user)
            action = "Updated"

        db.flush()
        print(f"{action} user: {user.email}")

    db.commit()

    print("Done.")


def main():
    """Main function"""
    print("\nStarting user seed script...")

    # Don't create tables here - they should already exist from migrations
    # Create database session
    db = SessionLocal()

    try:
        create_default_users(db)
    except Exception as e:
        print(f"\n❌ Error creating users: {e}")
        import traceback

        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
