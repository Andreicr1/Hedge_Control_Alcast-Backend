#!/usr/bin/env python3
"""
Reset development database - creates fresh schema and seed users.
Run from the backend/ directory.
"""
import os
import sys
from pathlib import Path

# Ensure we're in the backend directory
backend_dir = Path(__file__).parent
os.chdir(backend_dir)

# Force load .env before importing app modules
from dotenv import load_dotenv
load_dotenv(backend_dir / ".env", override=True)

# Always target the local sqlite dev DB for this script.
os.environ["DATABASE_URL"] = "sqlite:///./dev.db"

# Now import app modules
from app.database import Base, engine, SessionLocal
from app import models
from app.services.auth import hash_password

def main():
    db_path = backend_dir / "dev.db"
    
    # Remove existing database
    if db_path.exists():
        print(f"Removing existing database: {db_path}")
        db_path.unlink()

    # Create all tables (SQLAlchemy) to match current ORM models.
    # Alembic tasks are kept stable by the SQLite auto-stamp logic in alembic/env.py.
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created")
    
    # Create session
    db = SessionLocal()
    try:
        # Create roles
        print("Creating roles...")
        for role_name in models.RoleName:
            existing = db.query(models.Role).filter(models.Role.name == role_name).first()
            if not existing:
                db.add(models.Role(name=role_name))
        db.commit()
        print("✅ Roles created")
        
        # Create users
        print("Creating users...")
        users_data = [
            ("Admin", "admin@alcast.local", models.RoleName.admin),
            ("Financeiro", "financeiro@alcast.local", models.RoleName.financeiro),
            ("Comercial (alias compras)", "compras@alcast.local", models.RoleName.comercial),
            ("Comercial (alias vendas)", "vendas@alcast.local", models.RoleName.comercial),
            ("Auditoria", "auditoria@alcast.local", models.RoleName.auditoria),
        ]
        for name, email, role_name in users_data:
            existing = db.query(models.User).filter(models.User.email == email).first()
            if not existing:
                role = db.query(models.Role).filter(models.Role.name == role_name).first()
                user = models.User(
                    name=name,
                    email=email,
                    hashed_password=hash_password("123"),
                    role_id=role.id if role else None,
                )
                db.add(user)
                print(f"  Created user: {email}")
        db.commit()
        print("✅ Users created (password: 123)")
        
        print("\n🎉 Development database reset complete!")
        print(f"   Database: {db_path}")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
