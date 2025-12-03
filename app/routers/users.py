from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List
from app.database import get_db
from app.models.models import User, UserRole
from app.schemas.user_schema import UserCreate, UserResponse
from app.dependencies.dependencies_main import require_admin
from app.utils.auth import get_password_hash
import secrets

router = APIRouter(prefix="/users", tags=["Users"])


# ============================================================
# CREATE USER (ASYNC)
# ============================================================
@router.post("/create", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    # --- Check if email already exists ---
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # --- Generate temporary password ---
    temp_password = secrets.token_urlsafe(16)

    # --- Create new user ---
    new_user = User(
        email=user_data.email,
        password_hash=get_password_hash(temp_password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        org_id=admin.org_id,
        is_admin=False,
        created_by=admin.user_id,
        status="pending_activation"
    )

    db.add(new_user)
    await db.flush()   # ensure new_user.user_id is available

    # --- Assign roles ---
    for role_id in user_data.role_ids:
        role_entry = UserRole(
            user_id=new_user.user_id,
            role_id=role_id,
            assigned_by=admin.user_id
        )
        db.add(role_entry)

    # --- Commit changes ---
    await db.commit()
    await db.refresh(new_user)

    # TODO: Send temp password by email
    print(f"Temp password for {new_user.email}: {temp_password}")

    return new_user


# ============================================================
# LIST USERS (ASYNC)
# ============================================================
@router.get("/list", response_model=List[UserResponse])
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    query = select(User).where(User.org_id == admin.org_id)
    result = await db.execute(query)
    users = result.scalars().all()
    return users


# ============================================================
# DELETE USER (ASYNC)
# ============================================================
@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    # --- Fetch user ---
    result = await db.execute(
        select(User).where(
            User.user_id == user_id,
            User.org_id == admin.org_id
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete admin user"
        )

    # --- Delete roles first (optional depending on FK constraints) ---
    await db.execute(
        delete(UserRole).where(UserRole.user_id == user_id)
    )

    # --- Delete user ---
    await db.delete(user)
    await db.commit()

    return {"message": "User deleted successfully"}