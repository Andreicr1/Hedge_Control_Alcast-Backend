from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import models
from app.api.deps import get_current_user
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
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
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


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def signup(request: Request, payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Public signup must NOT allow privilege/role selection.
    # Only the safe default role is permitted; admin (and others) must be assigned via controlled process.
    if payload.role != models.RoleName.compras:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role assignment is not allowed via signup",
        )

    role = db.query(models.Role).filter(models.Role.name == models.RoleName.compras).first()
    if not role:
        role = models.Role(name=models.RoleName.compras, description="compras")
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
        {"email": user.email, "role": "compras"},
        db=db,
        request_id=request.headers.get("x-request-id"),
        ip=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    return user
