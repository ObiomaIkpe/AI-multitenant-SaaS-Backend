from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from datetime import datetime, timedelta
from app.database import get_db
from app.models.models import User, Organization, UserInvitation
from app.schemas.invite_schema import (
    InviteUserRequest, InviteUserResponse,
    ValidateInviteRequest, ValidateInviteResponse,
    CompleteSetupRequest, CompleteSetupResponse
)
from app.routers.auth import get_password_hash 
from app.dependencies.dependencies_main import require_org_owner
from app.utils.emails import send_invitation_email
import secrets

router = APIRouter(prefix="/invitations", tags=["Invitations"])


@router.post("/send", response_model=InviteUserResponse)
async def send_invitation(
    request: InviteUserRequest,
    background_tasks: BackgroundTasks,
    owner: User = Depends(require_org_owner),
    db: AsyncSession = Depends(get_db)
):
    """Send invitation to a new user. Owner only."""
    
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == request.email.lower())
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    # Check for pending invitation
    result = await db.execute(
        select(UserInvitation).where(
            UserInvitation.email == request.email.lower(),
            UserInvitation.org_id == owner.org_id,
            UserInvitation.accepted == False,
            UserInvitation.expires_at > datetime.utcnow()
        )
    )
    existing_invite = result.scalar_one_or_none()
    
    if existing_invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation already sent to this email"
        )
    
    # Check max users limit
    result = await db.execute(
        select(Organization).where(Organization.org_id == owner.org_id)
    )
    org = result.scalar_one()
    
    result = await db.execute(
        select(User).where(User.org_id == owner.org_id)
    )
    current_users = len(result.scalars().all())
    
    if current_users >= org.max_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization has reached maximum user limit ({org.max_users})"
        )
    
    # Generate secure token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    # Create invitation
    invitation = UserInvitation(
        org_id=owner.org_id,
        email=request.email.lower(),
        token=token,
        invited_by=owner.user_id,
        expires_at=expires_at
    )
    
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    
    # Send email in background
    background_tasks.add_task(
        send_invitation_email,
        email=request.email,
        token=token,
        org_name=org.org_name,
        inviter_name=f"{owner.first_name} {owner.last_name or ''}".strip()
    )
    
    return InviteUserResponse(
        invitation_id=invitation.invitation_id,
        email=invitation.email,
        expires_at=invitation.expires_at
    )


@router.post("/validate", response_model=ValidateInviteResponse)
async def validate_invitation(
    request: ValidateInviteRequest,
    db: AsyncSession = Depends(get_db)
):
    """Validate invitation token and return organization details."""
    
    result = await db.execute(
        select(UserInvitation, Organization).join(
            Organization,
            UserInvitation.org_id == Organization.org_id
        ).where(
            UserInvitation.token == request.token,
            UserInvitation.accepted == False,
            UserInvitation.expires_at > datetime.utcnow()
        )
    )
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation token"
        )
    
    invitation, organization = row
    
    return ValidateInviteResponse(
        valid=True,
        email=invitation.email,
        org_name=organization.org_name,
        expires_at=invitation.expires_at
    )


@router.post("/complete-setup", response_model=CompleteSetupResponse)
async def complete_setup(
    request: CompleteSetupRequest,
    db: AsyncSession = Depends(get_db)
):
    """Complete user setup with password and profile information."""
    
    # Validate token
    result = await db.execute(
        select(UserInvitation).where(
            UserInvitation.token == request.token,
            UserInvitation.accepted == False,
            UserInvitation.expires_at > datetime.utcnow()
        )
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation token"
        )
    
    # Check if user already exists (edge case)
    result = await db.execute(
        select(User).where(User.email == invitation.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists"
        )
    
    # Create new user
    password_hashed = get_password_hash(request.password)
    
    new_user = User(
        org_id=invitation.org_id,
        email=invitation.email,
        password_hash=password_hashed,
        first_name=request.first_name,
        last_name=request.last_name,
        middle_name=request.middle_name,
        email_verified=True,  # Auto-verify since they used valid invite
        created_by=invitation.invited_by,
        status="active"
    )
    
    db.add(new_user)
    
    # Mark invitation as accepted
    invitation.accepted = True
    invitation.accepted_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(new_user)
    
    return CompleteSetupResponse(
        user_id=new_user.user_id,
        email=new_user.email,
        first_name=new_user.first_name,
        org_id=new_user.org_id
    )


@router.get("/list", response_model=List[InviteUserResponse])
async def list_invitations(
    status_filter: Optional[str] = None,  # pending, accepted, expired, all
    owner: User = Depends(require_org_owner),
    db: AsyncSession = Depends(get_db)
):
    """List all invitations for the organization. Filter by status."""
    
    query = select(UserInvitation).where(
        UserInvitation.org_id == owner.org_id
    )
    
    now = datetime.utcnow()
    
    if status_filter == "pending":
        query = query.where(
            UserInvitation.accepted == False,
            UserInvitation.expires_at > now
        )
    elif status_filter == "accepted":
        query = query.where(UserInvitation.accepted == True)
    elif status_filter == "expired":
        query = query.where(
            UserInvitation.accepted == False,
            UserInvitation.expires_at <= now
        )
    # "all" or None returns everything
    
    query = query.order_by(UserInvitation.created_at.desc())
    
    result = await db.execute(query)
    invitations = result.scalars().all()
    
    return [
        InviteUserResponse(
            invitation_id=inv.invitation_id,
            email=inv.email,
            expires_at=inv.expires_at,
            message=_get_status(inv, now)
        )
        for inv in invitations
    ]


@router.delete("/{invitation_id}")
async def cancel_invitation(
    invitation_id: str,
    owner: User = Depends(require_org_owner),
    db: AsyncSession = Depends(get_db)
):
    """Cancel/delete a pending invitation. Owner only."""
    
    result = await db.execute(
        select(UserInvitation).where(
            UserInvitation.invitation_id == invitation_id,
            UserInvitation.org_id == owner.org_id
        )
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )
    
    if invitation.accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel an already accepted invitation"
        )
    
    await db.delete(invitation)
    await db.commit()
    
    return {"message": "Invitation cancelled successfully"}


@router.post("/{invitation_id}/resend")
async def resend_invitation(
    invitation_id: str,
    background_tasks: BackgroundTasks,
    owner: User = Depends(require_org_owner),
    db: AsyncSession = Depends(get_db)
):
    """Resend invitation email with a new token."""
    
    result = await db.execute(
        select(UserInvitation, Organization).join(
            Organization,
            UserInvitation.org_id == Organization.org_id
        ).where(
            UserInvitation.invitation_id == invitation_id,
            UserInvitation.org_id == owner.org_id
        )
    )
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )
    
    invitation, org = row
    
    if invitation.accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot resend an already accepted invitation"
        )
    
    # Generate new token and extend expiry
    invitation.token = secrets.token_urlsafe(32)
    invitation.expires_at = datetime.utcnow() + timedelta(days=7)
    
    await db.commit()
    
    # Resend email
    background_tasks.add_task(
        send_invitation_email,
        email=invitation.email,
        token=invitation.token,
        org_name=org.org_name,
        inviter_name=f"{owner.first_name} {owner.last_name or ''}".strip()
    )
    
    return {"message": "Invitation resent successfully"}


def _get_status(invitation: UserInvitation, now: datetime) -> str:
    """Helper to determine invitation status."""
    if invitation.accepted:
        return "Accepted"
    elif invitation.expires_at <= now:
        return "Expired"
    else:
        return "Pending"