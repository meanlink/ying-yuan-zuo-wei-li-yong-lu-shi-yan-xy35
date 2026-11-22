from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy import text
from .config import REDIS_URL
from .database import engine
from .middlewares.rate_limit import RateLimitMiddleware
from .middlewares.request_id import RequestIdMiddleware
from .routes import auth, observations, operations, plans
from .settlement import routes as settlement

app = FastAPI(title="影院座位利用率实验")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIdMiddleware)
app.include_router(auth.router, prefix="/api")
app.include_router(plans.router, prefix="/api")
app.include_router(operations.router, prefix="/api")
app.include_router(observations.router, prefix="/api")
app.include_router(settlement.router, prefix="/api")

@app.get("/health")
def health():
    with engine.connect() as conn: conn.execute(text("select 1"))
    Redis.from_url(REDIS_URL).ping()
    return {"status": "ok", "service": "backend"}

@app.get("/api/me")
def me():
    return {"service": "cinema-seat-experiment"}
