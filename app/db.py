"""Emotion database — connects to the `emotion` database on PostgreSQL."""

import os
import re
import psycopg2
import psycopg2.extras
from psycopg2 import pool

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "postgres"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "emotion"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(1, 5, **DB_CONFIG)
    return _pool


def _conn():
    c = _get_pool().getconn()
    c.autocommit = True
    return c


def _pg(sql):
    return re.sub(r'\$\d+', '%s', sql)


def q(sql, params=None, fetch="all"):
    sql = _pg(sql)
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            if fetch == "one":
                row = cur.fetchone()
                return dict(row) if row is not None else None
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return [] if fetch == "all" else None
    finally:
        _get_pool().putconn(conn)


def execute(sql, params=None):
    sql = _pg(sql)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return True
    except Exception:
        return False
    finally:
        _get_pool().putconn(conn)


def init_db():
    execute("CREATE EXTENSION IF NOT EXISTS vector")

    execute("""
        CREATE TABLE IF NOT EXISTS emotion_cache (
            id SERIAL PRIMARY KEY,
            label VARCHAR(100) UNIQUE NOT NULL,
            eye_curve REAL NOT NULL DEFAULT 0,
            eye_open REAL NOT NULL DEFAULT 0.5,
            eye_pupil REAL NOT NULL DEFAULT 0,
            mouth_curve REAL NOT NULL DEFAULT 0,
            mouth_open REAL NOT NULL DEFAULT 0,
            mouth_width REAL NOT NULL DEFAULT 0.8,
            sparkle REAL NOT NULL DEFAULT 0.5,
            brow_angle REAL NOT NULL DEFAULT 0,
            brow_height REAL NOT NULL DEFAULT 0.5,
            brow_asym REAL NOT NULL DEFAULT 0,
            reply TEXT NOT NULL DEFAULT '',
            sequence_data JSONB,
            use_count INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # Migration for missing columns
    for col, typ in [
        ("eye_pupil", "REAL NOT NULL DEFAULT 0"),
        ("brow_angle", "REAL NOT NULL DEFAULT 0"),
        ("brow_height", "REAL NOT NULL DEFAULT 0.5"),
        ("brow_asym", "REAL NOT NULL DEFAULT 0"),
        ("sequence_data", "JSONB"),
    ]:
        try:
            execute(f"ALTER TABLE emotion_cache ADD COLUMN IF NOT EXISTS {col} {typ}")
        except Exception:
            pass

    # Chat history
    execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            user_msg TEXT NOT NULL,
            avatar_reply TEXT NOT NULL DEFAULT '',
            emotion_label VARCHAR(100) NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Semantic memory vectors for similarity search
    execute("""
        CREATE TABLE IF NOT EXISTS memory_vectors (
            id SERIAL PRIMARY KEY,
            chat_id INTEGER NOT NULL REFERENCES chat_history(id),
            embedding halfvec(256),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    execute("""
        CREATE INDEX IF NOT EXISTS idx_memory_vectors_embedding
        ON memory_vectors USING hnsw (embedding halfvec_cosine_ops)
    """)

    # Diary entries
    execute("""
        CREATE TABLE IF NOT EXISTS diary_entries (
            id SERIAL PRIMARY KEY,
            date DATE UNIQUE NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            chat_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # News items
    execute("""
        CREATE TABLE IF NOT EXISTS news_items (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            source VARCHAR(50) NOT NULL DEFAULT '',
            rank INTEGER NOT NULL DEFAULT 0,
            fetched_at TIMESTAMP DEFAULT NOW()
        )
    """)
