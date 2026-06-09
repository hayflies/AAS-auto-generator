"""SQLite DB 헬퍼 — AAS 생성 결과를 저장/조회한다."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "aas_database.db"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS aas_results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id        TEXT    NOT NULL,
            asset_name      TEXT,
            created_at      TEXT    NOT NULL,
            property_count  INTEGER DEFAULT 0,
            aas_json        TEXT    NOT NULL,
            model_path      TEXT
        )
    """)
    # 기존 DB에 model_path 컬럼이 없으면 추가 (마이그레이션)
    try:
        conn.execute("ALTER TABLE aas_results ADD COLUMN model_path TEXT")
    except sqlite3.OperationalError:
        pass  # 이미 존재하면 무시
    conn.commit()
    conn.close()


def save_result(
    asset_id: str,
    asset_name: str,
    aas_json: dict,
    property_count: int = 0,
    model_path: str | None = None,
) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        """INSERT INTO aas_results
           (asset_id, asset_name, created_at, property_count, aas_json, model_path)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            asset_id,
            asset_name,
            datetime.now().isoformat(timespec="seconds"),
            property_count,
            json.dumps(aas_json, ensure_ascii=False),
            model_path,
        ),
    )
    result_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return result_id


def list_results() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, asset_id, asset_name, created_at, property_count, model_path "
        "FROM aas_results ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_result(result_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM aas_results WHERE id = ?", (result_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    result["aas_json"] = json.loads(result["aas_json"])
    return result


def delete_result(result_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("DELETE FROM aas_results WHERE id = ?", (result_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0
