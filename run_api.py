#!/usr/bin/env python3
"""
LandPPT API-only Mode Launcher
No authentication, pure REST API
"""

import os
import sys
import uvicorn

# Set API-only mode environment variables BEFORE importing app
os.environ.setdefault("DISABLE_AUTH", "true")
os.environ.setdefault("API_ONLY_MODE", "true")

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv

# Load .env file if exists
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)

# Also try to load .env.api
env_api_path = os.path.join(os.path.dirname(__file__), ".env.api")
if os.path.exists(env_api_path):
    load_dotenv(env_api_path, override=True)

if __name__ == "__main__":
    print("=" * 60)
    print("LandPPT API Server - Pure API Mode (No Authentication)")
    print("=" * 60)
    print()
    print(f"API Docs: http://localhost:{os.environ.get('PORT', 8000)}/docs")
    print(f"Redoc:    http://localhost:{os.environ.get('PORT', 8000)}/redoc")
    print(f"Health:   http://localhost:{os.environ.get('PORT', 8000)}/health")
    print()

    uvicorn.run(
        "src.landppt.main_api:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", 8000)),
        reload=os.environ.get("RELOAD", "false").lower() == "true",
        log_level=os.environ.get("LOG_LEVEL", "info"),
        workers=int(os.environ.get("WORKERS", 1)),
    )
