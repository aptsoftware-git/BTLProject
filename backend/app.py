from __future__ import annotations

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.routes import router

# Configure logging format and levels
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
backend_logger = logging.getLogger("backend")

# Initialize FastAPI App
app = FastAPI(
    title="AI Document Proofreading System API",
    description="Backend service for layout-aware document extraction, spelling check, and grammar validation.",
    version="1.0.0"
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(router, prefix="/api")

from fastapi.staticfiles import StaticFiles
from src.config import ROOT_DIR

output_dir = ROOT_DIR / "data" / "output"
output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(output_dir)), name="outputs")


@app.get("/", summary="Health Check API")
async def health_check():
    return {
        "status": "healthy",
        "service": "AI Document Proofreading System",
        "version": "1.0.0"
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler to intercept unhandled exceptions and format them as JSON."""
    backend_logger.error(
        "Unhandled exception occurred at path %s: %s",
        request.url.path,
        exc,
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred on the server.",
            "error_message": str(exc)
        }
    )
