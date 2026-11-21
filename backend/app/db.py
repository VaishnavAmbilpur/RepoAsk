import os
import sqlite3
from pathlib import Path
import libsql_client
from dotenv import load_dotenv

load_dotenv(override=False)

DEFAULT_DB_FILE = str(Path(__file__).resolve().parent.parent / "local.db")

class SQLiteClientWrapper:
    """Drop-in local SQLite client mimicking libsql_client interface on Windows."""
    def __init__(self, db_path: str = DEFAULT_DB_FILE):
        clean_path = db_path.replace("file:", "")
        self.conn = sqlite3.connect(clean_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        
    def execute(self, sql: str, params: list = None):
        cur = self.conn.cursor()
        if params is not None:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        self.conn.commit()
        rows = cur.fetchall()
        
        class Result:
            def __init__(self, r):
                self.rows = r
        return Result(rows)

    def batch(self, statements: list):
        """Executes a list of SQL statement tuples [(sql, params), ...] or strings."""
        cur = self.conn.cursor()
        for stmt in statements:
            if isinstance(stmt, (tuple, list)):
                sql = stmt[0]
                params = stmt[1] if len(stmt) > 1 else None
                if params is not None:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
            else:
                cur.execute(str(stmt))
        self.conn.commit()
        
    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


_USE_LOCAL_FALLBACK = os.getenv("USE_LOCAL_DB", "0") == "1"

def get_db():
    """Returns a database client (Turso Cloud if reachable, otherwise local SQLite)."""
    global _USE_LOCAL_FALLBACK
    
    db_url = os.getenv("TURSO_DATABASE_URL", "file:local.db")
    auth_token = os.getenv("TURSO_AUTH_TOKEN", "")
    
    # Use standard sqlite3 for local file database to prevent Python 3.13 Windows thread hangs
    if _USE_LOCAL_FALLBACK or db_url.startswith("file:") or not auth_token:
        return SQLiteClientWrapper(DEFAULT_DB_FILE)
    
    if db_url.startswith("libsql://"):
        db_url = db_url.replace("libsql://", "https://")
        
    try:
        client = libsql_client.create_client_sync(db_url, auth_token=auth_token)
        client.execute("SELECT 1")
        return client
    except Exception as e:
        print(f"Notice: Turso Cloud unreachable ({e}). Switching to local SQLite storage.")
        _USE_LOCAL_FALLBACK = True
        return SQLiteClientWrapper(DEFAULT_DB_FILE)

def init_db():
    """Initializes tables for repositories, files, and code chunks with automatic schema migration."""
    client = get_db()
    
    try:
        # 1. Repositories table
        client.execute("""
            CREATE TABLE IF NOT EXISTS repositories (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Files table
        client.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                path TEXT NOT NULL,
                total_lines INTEGER NOT NULL,
                content TEXT,
                FOREIGN KEY (repo_id) REFERENCES repositories(id)
            );
        """)

        # 3. Code Chunks table
        client.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                file_id TEXT,
                path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding TEXT NOT NULL,
                FOREIGN KEY (repo_id) REFERENCES repositories(id)
            );
        """)

        # Migration checks for columns in case of existing older databases
        if isinstance(client, SQLiteClientWrapper):
            cur = client.conn.cursor()
            cur.execute("PRAGMA table_info(files)")
            file_cols = [r[1] for r in cur.fetchall()]
            if "content" not in file_cols:
                cur.execute("ALTER TABLE files ADD COLUMN content TEXT")
                client.conn.commit()

            cur.execute("PRAGMA table_info(chunks)")
            chunk_cols = [r[1] for r in cur.fetchall()]
            if "file_id" not in chunk_cols:
                cur.execute("ALTER TABLE chunks ADD COLUMN file_id TEXT")
                client.conn.commit()
    except Exception as e:
        print(f"Database schema init warning: {e}")
    finally:
        client.close()
