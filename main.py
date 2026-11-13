import sqlite3
import time
from datetime import datetime, timezone
import threading
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI

CHECK_INTERVAL_SECONDS = 30


def monitor_loop():
    while True:
        for site in SITES:
            save_result(check(site))
        time.sleep(CHECK_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app):
    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()
    yield


app = FastAPI(lifespan=lifespan)
SITES = [
    "https://wikipedia.org",
    "https://google.com",
    "https://github.com",
]

DB_FILE = "monitor.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            is_up INTEGER,
            status_code INTEGER,
            response_time_ms INTEGER,
            checked_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


def save_result(result):
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT INTO checks (url, is_up, status_code, response_time_ms, checked_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            result["url"],
            int(result["is_up"]),
            result["status_code"],
            result["response_time_ms"],
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/check")
def check(url: str):
    start = time.time()
    try:
        response = httpx.get(url, timeout=5, follow_redirects=True)
        elapsed_ms = round((time.time() - start) * 1000)
        return {
            "url": url,
            "is_up": response.status_code < 400,
            "status_code": response.status_code,
            "response_time_ms": elapsed_ms,
        }
    except httpx.RequestError as e:
        elapsed_ms = round((time.time() - start) * 1000)
        return {
            "url": url,
            "is_up": False,
            "status_code": None,
            "response_time_ms": elapsed_ms,
            "error": str(e),
        }


@app.get("/check-all")
def check_all():
    results = [check(site) for site in SITES]
    for result in results:
        save_result(result)
    return results


@app.get("/history")
def history():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM checks ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return [
        {**dict(row), "is_up": bool(row["is_up"])}
        for row in rows
    ]