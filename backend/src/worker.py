import os, time
from pathlib import Path
from redis import Redis
from .config import REDIS_URL

Path("/shared").mkdir(exist_ok=True)
r = Redis.from_url(REDIS_URL, decode_responses=True)
while True:
    try:
        r.set("cinema-seat-worker", "alive", ex=30)
        Path("/shared/worker-heartbeat").touch()
    except Exception:
        pass
    time.sleep(5)
