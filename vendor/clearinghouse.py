# clearinghouse.py - provided. Do not modify.
import random
import sqlite3
import time
import uuid
from pathlib import Path

_DB = Path(__file__).with_name("clearinghouse.sqlite3")


class ClearinghouseError(Exception):
    """The clearinghouse rejected the request. Nothing was recorded."""


class ClearinghouseTimeout(Exception):
    """No response in time. The submission MAY have been recorded."""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB, timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS submissions "
        "(claim_reference TEXT, submission_id TEXT, amount TEXT, created_at REAL)"
    )
    return conn


def submit(claim_reference: str, amount: str) -> str:
    """Register a claim and return a submission ID.

    Every successful call creates a NEW submission, even for a reference
    that was already submitted. Duplicate submissions are billed.
    """
    time.sleep(random.uniform(0.2, 2.0))
    roll = random.random()
    if roll < 0.10:
        raise ClearinghouseError("Service unavailable")
    submission_id = f"CH-{uuid.uuid4().hex[:10].upper()}"
    with _conn() as conn:
        conn.execute(
            "INSERT INTO submissions VALUES (?, ?, ?, ?)",
            (claim_reference, submission_id, amount, time.time()),
        )
    if roll < 0.25:
        raise ClearinghouseTimeout("No response from clearinghouse")
    return submission_id


def lookup(claim_reference: str) -> list[str]:
    """Return every submission ID recorded for a claim reference, oldest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT submission_id FROM submissions "
            "WHERE claim_reference = ? ORDER BY created_at",
            (claim_reference,),
        ).fetchall()
    return [r[0] for r in rows]
