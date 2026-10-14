# db.py
import os
import sqlite3
from config import DB_PATH, DATA_DIR


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_text TEXT NOT NULL,
                scene TEXT,
                result_json TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)


def add_favorite(original_text: str, scene: str, result_json: str) -> int:
    with _get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO favorites (original_text, scene, result_json) VALUES (?, ?, ?)",
            (original_text, scene, result_json)
        )
        return cur.lastrowid


def get_all_favorites() -> list:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM favorites ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_favorite(fav_id: int) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM favorites WHERE id=?", (fav_id,)
        ).fetchone()
        return dict(row) if row else None


def delete_favorite(fav_id: int):
    with _get_conn() as conn:
        conn.execute("DELETE FROM favorites WHERE id=?", (fav_id,))
