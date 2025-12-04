from app.schemas.role_schema import RoleUpdate  # You'll need this schema
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List, Union
from app.database import get_db
from app.models.models import Role, User
from app.schemas.role_schema import RoleCreate, RoleResponse
from app.dependencies.dependencies_main import require_admin, require_org_owner

router = APIRouter(prefix="/roles", tags=["Roles"])


# ============================================================
# CREATE ROLE(S) — ASYNC
# ============================================================
@router.post("/create", response_model=Union[RoleResponse, List[RoleResponse]])
async def create_role(
    role_data: Union[RoleCreate, List[RoleCreate]],
    owner: User = Depends(require_org_owner),
    db: AsyncSession = Depends(get_db)
):
    is_single = isinstance(role_data, RoleCreate)
    roles_list = [role_data] if is_single else role_data

    if not roles_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No roles provided"
        )

    role_names = [r.role_name for r in roles_list]
    role_names_lower = [name.lower() for name in role_names]

    if len(role_names_lower) != len(set(role_names_lower)):
        duplicates = [
            name for name in role_names
            if role_names_lower.count(name.lower()) > 1
        ]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Duplicate role names in request: {', '.join(set(duplicates))}"
        )

    existing_query = select(Role).where(
        Role.org_id == owner.org_id,
        func.lower(Role.role_name).in_(role_names_lower)
    )
    result = await db.execute(existing_query)
    existing_roles = result.scalars().all()

    if existing_roles:
        existing_names = [role.role_name for role in existing_roles]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Roles already exist: {', '.join(existing_names)}"
        )

    created_roles = []
    for role in roles_list:
        new_role = Role(
            org_id=owner.org_id,
            role_name=role.role_name,
            description=role.description,
            created_by=owner.user_id
        )
        db.add(new_role)
        created_roles.append(new_role)

    await db.commit()

    for role in created_roles:
        await db.refresh(role)

    return created_roles[0] if is_single else created_roles


@router.get("/list", response_model=List[RoleResponse])
async def list_roles(
    owner: User = Depends(require_org_owner),
    db: AsyncSession = Depends(get_db)
):
    query = select(Role).where(Role.org_id == owner.org_id)
    result = await db.execute(query)
    roles = result.scalars().all()
    return roles


@router.delete("/{role_id}")
async def delete_role(
    role_id: str,
    owner: User = Depends(require_org_owner),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Role).where(
            Role.role_id == role_id,
            Role.org_id == owner.org_id
        )
    )
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    if role.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete default role"
        )

    await db.delete(role)
    await db.commit()

    return {"message": "Role deleted successfully"}


@router.patch("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: str,
    role_data: RoleUpdate,
    owner: User = Depends(require_org_owner),
    db: AsyncSession = Depends(get_db)
):
    """Update role name and/or description. Owner only."""
    
    # Fetch the role
    result = await db.execute(
        select(Role).where(
            Role.role_id == role_id,
            Role.org_id == owner.org_id
        )
    )
    role = result.scalar_one_or_none()
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Check if updating role name
    if role_data.role_name:
        # Prevent updating default role name
        if role.is_default:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rename default role"
            )
        
        # Check for duplicate role name (case-insensitive)
        existing_query = select(Role).where(
            Role.org_id == owner.org_id,
            func.lower(Role.role_name) == role_data.role_name.lower(),
            Role.role_id != role_id  # Exclude current role
        )
        result = await db.execute(existing_query)
        existing_role = result.scalar_one_or_none()
        
        if existing_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role name '{role_data.role_name}' already exists"
            )
        
        role.role_name = role_data.role_name
    
    # Update description if provided
    if role_data.description is not None:
        role.description = role_data.description
    
    await db.commit()
    await db.refresh(role)
    
    return role


# ============================================================
# ASSIGN ROLE TO USER
# ============================================================
@router.post("/{role_id}/assign/{user_id}")
async def assign_role_to_user(
    role_id: str,
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from app.models.models import UserRole
    
    # Verify role exists in org
    role_result = await db.execute(
        select(Role).where(Role.role_id == role_id, Role.org_id == admin.org_id)
    )
    role = role_result.scalar_one_or_none()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Verify user exists in org
    user_result = await db.execute(
        select(User).where(User.user_id == user_id, User.org_id == admin.org_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found in organization")
    
    # Check if already assigned
    existing = await db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Role already assigned")
    
    user_role = UserRole(
        user_id=user_id,
        role_id=role_id,
        assigned_by=admin.user_id
    )
    db.add(user_role)
    await db.commit()
    
    return {"message": "Role assigned successfully"}


# ============================================================
# REMOVE ROLE FROM USER
# ============================================================
@router.delete("/{role_id}/remove/{user_id}")
async def remove_role_from_user(
    role_id: str,
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from app.models.models import UserRole
    
    # Verify role and user in same org
    role_result = await db.execute(
        select(Role).where(Role.role_id == role_id, Role.org_id == admin.org_id)
    )
    if not role_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Role not found")
    
    user_result = await db.execute(
        select(User).where(User.user_id == user_id, User.org_id == admin.org_id)
    )
    if not user_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")
    
    # Delete assignment
    result = await db.execute(
        delete(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id
        )
    )
    
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    
    await db.commit()
    return {"message": "Role removed successfully"}


# ============================================================
# GET USERS WITH SPECIFIC ROLE
# ============================================================
@router.get("/{role_id}/users")
async def get_role_users(
    role_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from app.models.models import UserRole
    
    # Verify role exists
    role_result = await db.execute(
        select(Role).where(Role.role_id == role_id, Role.org_id == admin.org_id)
    )
    role = role_result.scalar_one_or_none()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Get users with this role
    result = await db.execute(
        select(User).join(UserRole).where(UserRole.role_id == role_id)
    )
    users = result.scalars().all()
    
    return {
        "role": role,
        "users": users
    }


# ============================================================
# GET USER'S ROLES
# ============================================================
@router.get("/user/{user_id}/roles")
async def get_user_roles(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from app.models.models import UserRole
    
    # Verify user in same org
    user_result = await db.execute(
        select(User).where(User.user_id == user_id, User.org_id == admin.org_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user's roles
    result = await db.execute(
        select(Role).join(UserRole).where(UserRole.user_id == user_id)
    )
    roles = result.scalars().all()
    
    return {
        "user": user,
        "roles": roles
    }