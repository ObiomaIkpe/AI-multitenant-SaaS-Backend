from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine
from app.config import settings

# --- Async Engine for FastAPI
ASYNC_ENGINE = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(
    bind=ASYNC_ENGINE,
    class_=AsyncSession,
    expire_on_commit=False
)

# --- Sync Engine for Celery
SYNC_ENGINE = create_engine(
    settings.DATABASE_URL.replace("+asyncpg", ""),  # remove asyncpg
    pool_pre_ping=True
)

SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=SYNC_ENGINE)

Base = declarative_base()

# Dependency for FastAPI
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# Dependency for Celery
def get_sync_db():
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()
