from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import stripe
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.models import User, UserRole, Organization, Role
from app.schemas.orginization_schema import OrganizationCreate, OrganizationResponse, OrganizationResponseTesting, SubscriptionUpgrade, TransferOwnership
from app.dependencies.dependencies_main import get_current_user
from app.utils.enums import SubscriptionStatus, SubscriptionTier
from app.config import settings

import app.stripe.stripe_utils as stripe_utils
import anyio

router = APIRouter(prefix="/organizations", tags=["Organizations"])

stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post("/create", response_model=OrganizationResponseTesting)
async def create_organization(
    org_data: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.org_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already belong to an organization. One organization per account.",
        )

    try:
        # 1️⃣ Create organization
        new_org = Organization(
            org_name=org_data.org_name,
            billing_email=org_data.billing_email,
            owner_user_id=current_user.user_id,
            subscription_status=org_data.subscription_status or SubscriptionStatus.trial,
            subscription_tier=org_data.subscription_tier or SubscriptionTier.free,
            max_users=org_data.max_users,
            logo_url=org_data.logo_url,
            favicon_url=org_data.favicon_url,
            theme_color=org_data.theme_color,
            domain=org_data.domain,
        )
        db.add(new_org)
        await db.flush()

        # 2️⃣ Stripe integration
        stripe_customer_id = await anyio.to_thread.run_sync(
            stripe_utils.create_organization_in_stripe,
            new_org.org_name,
            new_org.billing_email,
        )
        new_org.stripe_customer_id = stripe_customer_id

        if new_org.subscription_tier != SubscriptionTier.free:
            await anyio.to_thread.run_sync(
                stripe_utils.create_subscription,
                new_org,
                new_org.subscription_tier,
            )

        # 3️⃣ Assign owner user
        current_user.org_id = new_org.org_id
        current_user.is_admin = True

        # 4️⃣ Create default role
        default_role = Role(
            org_id=new_org.org_id,
            role_name="Member",
            description="Default role for all users",
            created_by=current_user.user_id,
            is_default=True,
        )
        db.add(default_role)
        await db.flush()

        # 5️⃣ Assign role to owner
        user_role = UserRole(
            user_id=current_user.user_id,
            role_id=default_role.role_id,
            assigned_by=current_user.user_id,
        )
        db.add(user_role)
        
        # Commit everything atomically
        await db.commit()
        await db.refresh(new_org)
        return new_org

    except Exception as e:
        await db.rollback()
        
        # Provide specific error messages
        if isinstance(e, IntegrityError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Database constraint violated: {str(e.orig)}",
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create organization: {str(e)}"
        )


# ============================================================
# GET MY ORGANIZATION — ASYNC
# ============================================================
@router.get("/my-organization", response_model=OrganizationResponse)
async def get_my_organization(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You don't have an organization yet"
        )

    # Query organization
    result = await db.execute(
        select(Organization).where(Organization.org_id == current_user.org_id)
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    return org


from app.schemas.orginization_schema import OrganizationUpdate  # Add to imports

@router.patch("/update", response_model=OrganizationResponse)
async def update_organization(
    org_update: OrganizationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You don't belong to an organization"
        )
    
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    result = await db.execute(
        select(Organization).where(Organization.org_id == current_user.org_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    
    # Update only provided fields
    for field, value in org_update.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    
    await db.commit()
    await db.refresh(org)
    return org


from app.schemas.orginization_schema import (
    SubscriptionUpgrade, 
    TransferOwnership
)

# ============================================================
# UPGRADE SUBSCRIPTION
# ============================================================
@router.post("/upgrade")
async def upgrade_subscription(
    upgrade_data: SubscriptionUpgrade,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail="No organization found")
    
    result = await db.execute(
        select(Organization).where(Organization.org_id == current_user.org_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Require owner or admin
    if org.owner_user_id != current_user.user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Owner/admin access required")
    
    # Validate tier transition
    if upgrade_data.new_tier == org.subscription_tier:
        raise HTTPException(status_code=400, detail="Already on this tier")
    
    try:
        # Cancel existing subscription if exists
        if org.stripe_subscription_id:
            await anyio.to_thread.run_sync(
                stripe_utils.cancel_subscription,
                org.stripe_subscription_id
            )
        
        # Create new subscription
        if upgrade_data.new_tier != SubscriptionTier.free:
            subscription = await anyio.to_thread.run_sync(
                stripe_utils.create_subscription,
                org,
                upgrade_data.new_tier,
            )
            org.stripe_subscription_id = subscription.get("id")
            org.subscription_status = SubscriptionStatus.active
        else:
            org.stripe_subscription_id = None
            org.subscription_status = SubscriptionStatus.trial
        
        org.subscription_tier = upgrade_data.new_tier
        
        await db.commit()
        await db.refresh(org)
        
        return {
            "message": f"Upgraded to {upgrade_data.new_tier.value}",
            "organization": org
        }
    
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Upgrade failed: {str(e)}"
        )


# ============================================================
# GET BILLING PORTAL
# ============================================================
@router.get("/billing-portal")
async def get_billing_portal(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail="No organization found")
    
    result = await db.execute(
        select(Organization).where(Organization.org_id == current_user.org_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Require owner or admin
    if org.owner_user_id != current_user.user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Owner/admin access required")
    
    if not org.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer found")
    
    try:
        portal_url = await anyio.to_thread.run_sync(
            stripe_utils.create_billing_portal_session,
            org.stripe_customer_id
        )
        return {"url": portal_url}
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create portal session: {str(e)}"
        )


# ============================================================
# CANCEL SUBSCRIPTION
# ============================================================
@router.post("/cancel-subscription")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail="No organization found")
    
    result = await db.execute(
        select(Organization).where(Organization.org_id == current_user.org_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Require owner or admin
    if org.owner_user_id != current_user.user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Owner/admin access required")
    
    if not org.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription")
    
    try:
        await anyio.to_thread.run_sync(
            stripe_utils.cancel_subscription,
            org.stripe_subscription_id
        )
        
        org.stripe_subscription_id = None
        org.subscription_tier = SubscriptionTier.free
        org.subscription_status = SubscriptionStatus.cancelled
        
        await db.commit()
        await db.refresh(org)
        
        return {
            "message": "Subscription cancelled",
            "organization": org
        }
    
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Cancellation failed: {str(e)}"
        )


# ============================================================
# TRANSFER OWNERSHIP
# ============================================================
@router.post("/transfer-ownership")
async def transfer_ownership(
    transfer_data: TransferOwnership,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail="No organization found")
    
    result = await db.execute(
        select(Organization).where(Organization.org_id == current_user.org_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Only current owner can transfer
    if org.owner_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Only owner can transfer ownership")
    
    # Verify target user exists and is admin in same org
    target_result = await db.execute(
        select(User).where(
            User.user_id == transfer_data.new_owner_id,
            User.org_id == org.org_id
        )
    )
    target_user = target_result.scalar_one_or_none()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found in organization")
    
    if not target_user.is_admin:
        raise HTTPException(status_code=400, detail="Target user must be an admin")
    
    if target_user.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot transfer to yourself")
    
    try:
        org.owner_user_id = target_user.user_id
        
        await db.commit()
        await db.refresh(org)
        
        # TODO: Send email notifications to both users
        
        return {
            "message": f"Ownership transferred to {target_user.email}",
            "organization": org
        }
    
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Transfer failed: {str(e)}"
        )