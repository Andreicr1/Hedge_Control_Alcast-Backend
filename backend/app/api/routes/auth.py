from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import models
from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.schemas import Token, UserCreate, UserRead
from app.services.audit import audit_event
from app.services.auth import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=Token)
def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # When running in Entra-only mode, disable local password login.
    if str(settings.auth_mode or "local").strip().lower() == "entra":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    try:
        user = db.query(models.User).filter(models.User.email == form_data.username).first()
    except SQLAlchemyError:
        audit_event(
            "auth.login_db_error",
            None,
            {"email": form_data.username},
            db=db,
            request_id=request.headers.get("x-request-id"),
            ip=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Banco de dados indisponível ou não inicializado. Tente novamente em alguns instantes.",
        )
    if not user or not verify_password(form_data.password, user.hashed_password):
        audit_event(
            "auth.login_failed",
            None,
            {"email": form_data.username},
            db=db,
            request_id=request.headers.get("x-request-id"),
            ip=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )
    if not user.active:
        audit_event(
            "auth.login_inactive",
            user.id,
            {"email": user.email},
            db=db,
            request_id=request.headers.get("x-request-id"),
            ip=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    access_token = create_access_token(subject=user.email)
    audit_event(
        "auth.login_success",
        user.id,
        {"email": user.email},
        db=db,
        request_id=request.headers.get("x-request-id"),
        ip=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    return Token(access_token=access_token)


@router.get("/me")
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role.name if current_user.role else None,
    }

@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def signup(request: Request, payload: UserCreate, db: Session = Depends(get_db)):
    # When running in Entra-only mode, disable local signup.
    if str(settings.auth_mode or "local").strip().lower() == "entra":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Public signup must NOT allow privilege/role selection.
    # Only the safe default role is permitted; admin (and others) must be assigned via controlled process.
    if payload.role != models.RoleName.comercial:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role assignment is not allowed via signup",
        )

    role = db.query(models.Role).filter(models.Role.name == models.RoleName.comercial).first()
    if not role:
        role = models.Role(name=models.RoleName.comercial, description="comercial")
        db.add(role)
        db.flush()

    user = models.User(
        email=payload.email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
        role_id=role.id,
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit_event(
        "auth.signup",
        user.id,
        {"email": user.email, "role": "comercial"},
        db=db,
        request_id=request.headers.get("x-request-id"),
        ip=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    return user
