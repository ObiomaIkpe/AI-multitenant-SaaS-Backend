from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.models import User, Organization
from app.utils.auth import decode_access_token
from uuid import UUID
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

security = HTTPBearer()

async def get_current_user(  # ← Added async
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db: AsyncSession = Depends(get_db)  # ← Changed from Session
) -> User:
    
    logger.info("=" * 50)
    logger.info("get_current_user called")
    logger.info(f"Credentials received: {credentials}")
    logger.info(f"Token (first 20 chars): {credentials.credentials[:20] if credentials and credentials.credentials else 'None'}...")
    
    token = credentials.credentials
    
    logger.info("Attempting to decode token...")
    payload = decode_access_token(token)
    
    logger.info(f"Decoded payload: {payload}")

    if payload is None:
        logger.error("❌ Payload is None - token decode failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authentication Credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user_id: str = payload.get("sub")
    logger.info(f"User ID from token: {user_id}")
    
    if user_id is None:
        logger.error("❌ No 'sub' in payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    logger.info(f"Querying database for user_id: {user_id}")
    
    try:
        # ← Changed to async SQLAlchemy 2.0 syntax
        result = await db.execute(
            select(User).where(User.user_id == UUID(user_id))
        )
        user = result.scalar_one_or_none()
        logger.info(f"Database query result: {user}")
    except Exception as e:
        logger.error(f"❌ Database query error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Database error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    if user is None:
        logger.error(f"❌ User not found with ID: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    logger.info(f"✅ User found: {user.email}")
    
    # check user subscription
    if user.org_id:
        # ← Changed to async query
        result = await db.execute(
            select(Organization).where(Organization.org_id == user.org_id)
        )
        org = result.scalar_one_or_none()
        
        if org and org.subscription_status == "suspended":
            logger.warning(f"⚠️ User's organization is suspended")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account suspended - payment required"
            )
    
    logger.info("✅ Authentication successful")
    logger.info("=" * 50)
    return user


async def require_admin(  # ← Added async
    current_user: User = Depends(get_current_user)
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_current_tenant(  # ← Added async
    current_user = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)  # ← Changed from Session
) -> Organization:
    """
    Get the current user's organization/tenant.
    Raises 404 if user has no org_id or organization not found.
    """
    
    logger.info(f"get_current_tenant called for user: {current_user.email}")
    
    if not current_user.org_id:
        logger.error(f"❌ User {current_user.user_id} has no organization")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not associated with any organization"
        )
    
    try:
        # ← Changed to async query
        result = await db.execute(
            select(Organization).where(Organization.org_id == current_user.org_id)
        )
        org = result.scalar_one_or_none()
        
        if not org:
            logger.error(f"❌ Organization {current_user.org_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found"
            )
        
        logger.info(f"✅ Organization found: {org.org_id}")
        return org
        
    except Exception as e:
        logger.error(f"❌ Database error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )


async def require_org_owner(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Verify user is the organization owner"""
    if not current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must belong to an organization"
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
    
    if org.owner_user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organization owner can perform this action"
        )
    
    return current_user