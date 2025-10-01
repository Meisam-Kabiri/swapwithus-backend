"""
SwapWithUs Backend API
FastAPI application with your SPEED + SECURITY architecture
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from lib.api import listings, users, search, auth
from lib.database.schema import create_users_table, create_listings_table, create_enhanced_indexes
from pydantic import BaseModel

# Initialize FastAPI app
app = FastAPI(
    title="SwapWithUs API",
    description="High-performance swap platform with JSON category support",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(listings.router)
app.include_router(users.router)
app.include_router(search.router)
app.include_router(auth.router)

@app.on_event("startup")
async def startup_event():
    """Initialize database tables and indexes on startup"""
    try:
        await create_users_table()
        await create_listings_table()
        await create_enhanced_indexes()
        print("✅ Database initialization complete!")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")

@app.get("/")
async def root():
    return {
        "message": "SwapWithUs API",
        "version": "1.0.0",
        "architecture": "SPEED + SECURITY with asyncpg + SQLAlchemy Core"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "database": "connected"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
