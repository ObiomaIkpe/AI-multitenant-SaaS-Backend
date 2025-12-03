from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import auth, organizations, users, roles, document, user_invites
from app.api.local_embeddings import router as embeddings_router

app = FastAPI(
    title=settings.APP_NAME,
    description="API for Private AI SaaS",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(document.router)
app.include_router(user_invites.router)

# Include local embedding service only if not using Ollama
if not settings.USE_OLLAMA:
    try:
        from app.api.local_embeddings import router as local_embeddings_router
        app.include_router(local_embeddings_router, prefix="/local")
        print("✅ Local embedding service enabled at /local/embeddings")
    except ImportError:
        print("⚠️  sentence-transformers not installed. Local embedding service disabled.")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Extract messages from the list of errors
    errors = [f"{'.'.join(map(str, e['loc'][1:]))}: {e['msg']}" for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"detail": ", ".join(errors)}  # Join them into a single string
    )


@app.get("/")
async def root():
    return {"message": "Private AI SaaS API", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}