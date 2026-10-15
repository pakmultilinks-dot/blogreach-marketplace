import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

# Vercel serverless entrypoint. Set DATABASE_URL (Postgres) and SECRET_KEY
# in the Vercel project settings; the local SQLite file is ephemeral.
