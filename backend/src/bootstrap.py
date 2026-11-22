import time
from sqlalchemy import text
from .database import Base, engine
from . import operations_models  # Registers the operational tables before create_all.
from .settlement import models as settlement_models  # Registers the pilot settlement table.
from .config import SEED_DEMO

def bootstrap():
    for attempt in range(30):
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT pg_advisory_xact_lock(1057002)"))
                Base.metadata.create_all(conn)
            break
        except Exception:
            if attempt == 29:
                raise
            time.sleep(2)
    if SEED_DEMO:
        from scripts.seed_demo import seed
        seed()

if __name__ == "__main__":
    bootstrap()
