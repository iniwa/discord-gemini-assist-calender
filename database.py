# database.py
import sqlite3
import os
import threading

DB_FILE = "/data/tokens.sqlite3"
db_lock = threading.Lock()

def init_db():
    """データベースの初期化を行う"""
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)

    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # ユーザーごとのカレンダーIDを保存するテーブル
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_calendars (
            discord_id TEXT PRIMARY KEY,
            calendar_id TEXT NOT NULL
        )
        """)

        # Botの対話状態を管理するテーブル
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_states (
            discord_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.commit()
        conn.close()
        print("Database initialized.")

# --- カレンダーID管理 ---

def save_calendar_id(discord_id: str, calendar_id: str):
    """ユーザーのカレンダーIDを保存または更新する"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO user_calendars (discord_id, calendar_id)
        VALUES (?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET calendar_id=excluded.calendar_id
        """, (discord_id, calendar_id))
        conn.commit()
        conn.close()

def get_calendar_id(discord_id: str) -> str | None:
    """ユーザーのカレンダーIDを取得する"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT calendar_id FROM user_calendars WHERE discord_id = ?", (discord_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

def delete_calendar_id(discord_id: str) -> bool:
    """ユーザーのカレンダーIDを削除する。削除した場合Trueを返す。"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_calendars WHERE discord_id = ?", (discord_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

# --- 対話状態管理 ---

def set_user_state(discord_id: str, state: str):
    """ユーザーの状態を設定する"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO user_states (discord_id, state)
        VALUES (?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET state=excluded.state, timestamp=CURRENT_TIMESTAMP
        """, (discord_id, state))
        conn.commit()
        conn.close()

def get_user_state(discord_id: str) -> str | None:
    """ユーザーの状態を取得する"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT state FROM user_states WHERE discord_id = ?", (discord_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

def clear_user_state(discord_id: str):
    """ユーザーの状態を削除する"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_states WHERE discord_id = ?", (discord_id,))
        conn.commit()
        conn.close()

def get_stale_users(minutes: int) -> list[str]:
    """指定した分数が経過した古い状態のユーザーIDリストを取得する"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT discord_id FROM user_states
        WHERE timestamp < datetime('now', '-{minutes} minutes')
        """)
        results = cursor.fetchall()
        conn.close()
        return [r[0] for r in results]
