"""FastAPI backend for Market Analyzer.

Exposes REST API endpoints for:
- Market data (S&P 500 quotes, scoring, stock details)
- Portfolio management (holdings, transactions, Plaid integration)
- LLM assistant (sector and stock analysis)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from backend.api import market, portfolio, llm, plaid
from app.portfolio_db import init_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield


app = FastAPI(
    title="Market Analyzer API",
    description="Backend API for Market Analyzer - S&P 500 ranking, portfolio tracking, and AI analysis",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router, prefix="/api/market", tags=["market"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(llm.router, prefix="/api/llm", tags=["llm"])
app.include_router(plaid.router, prefix="/api/plaid", tags=["plaid"])


@app.get("/")
async def root():
    return {
        "name": "Market Analyzer API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
