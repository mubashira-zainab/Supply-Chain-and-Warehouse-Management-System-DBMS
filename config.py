"""
Central configuration — every secret is read from environment variables.
Locally they come from a `.env` file (project root, next to app.py).
On Vercel they come from Project Settings -> Environment Variables.
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()   # no-op on Vercel (no .env file there) — real env vars are used

# ── Flask ────────────────────────────────────────────────────
SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-only-insecure-key'

# ── Database ─────────────────────────────────────────────────
DATABASE_URL    = os.environ.get('DATABASE_URL')          # cloud (Neon / Supabase / Render ...)
AI_DATABASE_URL = os.environ.get('AI_DATABASE_URL')       # optional read-only role for the AI
DB_CONFIG = {
    'host':     os.environ.get('DB_HOST', 'localhost'),
    'port':     int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'supply_chain_db'),
    'user':     os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

# ── AI assistant (keys live ONLY on the server) ──────────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
GROQ_API_KEY   = os.environ.get('GROQ_API_KEY', '').strip()
AI_PROVIDER    = os.environ.get('AI_PROVIDER', 'auto').strip().lower()
GEMINI_MODELS  = [m.strip() for m in os.environ.get(
    'GEMINI_MODELS', 'gemini-1.5-flash,gemini-1.5-flash-8b,gemini-1.5-pro').split(',') if m.strip()]
GROQ_MODELS    = [m.strip() for m in os.environ.get(
    'GROQ_MODELS', 'llama3-70b-8192,llama3-8b-8192,mixtral-8x7b-32768').split(',') if m.strip()]


def _connect(url=None):
    if url:
        # Some hosts give "postgres://", psycopg2 needs "postgresql://"
        return psycopg2.connect(url.replace('postgres://', 'postgresql://', 1),
                                connect_timeout=10)
    return psycopg2.connect(connect_timeout=10, **DB_CONFIG)


def get_db(readonly_ai=False):
    """Return a new database connection with clear, human-readable errors."""
    try:
        if readonly_ai and AI_DATABASE_URL:
            return _connect(AI_DATABASE_URL)
        return _connect(DATABASE_URL)
    except psycopg2.OperationalError as e:
        err = str(e)
        if 'password authentication' in err:
            raise ConnectionError("Wrong database password! Check DB_PASSWORD / DATABASE_URL in .env")
        elif 'could not connect' in err or 'Connection refused' in err:
            raise ConnectionError("PostgreSQL is not reachable! Start PostgreSQL or check DATABASE_URL.")
        elif 'does not exist' in err:
            raise ConnectionError("Database does not exist! Run database/schema.sql first.")
        else:
            raise ConnectionError(f"Database error: {err}")


def ai_configured():
    return bool(GEMINI_API_KEY or GROQ_API_KEY)
