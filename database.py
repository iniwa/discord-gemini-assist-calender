# database.py
import sqlite3
import os
import threading

DB_FILE = "/data/tokens.sqlite3"
db_lock = threading.Lock()

def init_db():
    """データベースの初期化を行う"""
    # データディレクトリが存在しない場合は作成
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    if os.path.exists(DB_FILE):
        return
    
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # ユーザー認証情報を保存するテーブル
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tokens (
            discord_id TEXT PRIMARY KEY,
            google_token TEXT NOT NULL
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

def save_token(discord_id: str, google_token: str):
    """ユーザーのGoogle認証トークンを保存または更新する"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO user_tokens (discord_id, google_token)
        VALUES (?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET google_token=excluded.google_token
        """, (discord_id, google_token))
        conn.commit()
        conn.close()

def get_token(discord_id: str) -> str | None:
    """ユーザーのGoogle認証トークンを取得する"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT google_token FROM user_tokens WHERE discord_id = ?", (discord_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

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
        # SQLiteの datetime('now') はUTCなので注意。ここではシンプルに差分で見ます。
        cursor.execute(f"""
        SELECT discord_id FROM user_states 
        WHERE timestamp < datetime('now', '-{minutes} minutes')
        """)
        results = cursor.fetchall()
        conn.close()
        return [r[0] for r in results]
