import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://cinema:cinema_pass@db:5432/cinema")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
JWT_SECRET = os.getenv("JWT_SECRET", "cinema-seat-secret")
JWT_ALGORITHM = "HS256"
SEED_DEMO = os.getenv("SEED_DEMO", "true").lower() == "true"
