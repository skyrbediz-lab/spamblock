import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "spamblock.db"))


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS spam_numbers (
                phone TEXT PRIMARY KEY,
                source TEXT,
                report_count INTEGER DEFAULT 1,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                twilio_number TEXT UNIQUE NOT NULL,
                forward_to TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS call_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                from_number TEXT,
                to_number TEXT,
                action TEXT,
                reason TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            );

            CREATE INDEX IF NOT EXISTS idx_calllog_customer ON call_log(customer_id);
            CREATE INDEX IF NOT EXISTS idx_calllog_time ON call_log(timestamp);
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_spam(phone: str) -> tuple[bool, str | None]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT source, report_count FROM spam_numbers WHERE phone = ?",
            (normalize(phone),),
        ).fetchone()
    if row:
        return True, f"{row['source']} ({row['report_count']} reports)"
    return False, None


def get_customer_by_twilio_number(twilio_number: str):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM customers WHERE twilio_number = ? AND active = 1",
            (normalize(twilio_number),),
        ).fetchone()


def log_call(customer_id, from_number, to_number, action, reason):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO call_log (customer_id, from_number, to_number, action, reason) VALUES (?, ?, ?, ?, ?)",
            (customer_id, from_number, to_number, action, reason),
        )


def add_spam_number(phone: str, source: str = "manual"):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO spam_numbers (phone, source) VALUES (?, ?)
               ON CONFLICT(phone) DO UPDATE SET
                 report_count = report_count + 1,
                 last_seen = CURRENT_TIMESTAMP""",
            (normalize(phone), source),
        )


def add_customer(name, email, twilio_number, forward_to):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO customers (name, email, twilio_number, forward_to) VALUES (?, ?, ?, ?)",
            (name, email, normalize(twilio_number), normalize(forward_to)),
        )
        return cur.lastrowid


def normalize(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    return digits
