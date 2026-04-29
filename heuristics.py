"""
Heuristic spam detection for numbers NOT in the database.

This catches the long tail: spoofed callers, brand-new robocaller batches,
neighbor-spoofing scams. None of these will be in any spam DB on day 1
because they rotate constantly.

Each heuristic returns (is_spam: bool, reason: str | None, confidence: float).
The caller can choose a threshold (we default to 0.7).
"""
from __future__ import annotations

# Numbers reserved by the FCC for testing / fictional use.
# A real call will never originate from one of these.
RESERVED_PREFIXES = {
    "555010", "555011", "555012", "555013", "555014", "555015",
    "555016", "555017", "555018", "555019",
}

# Toll-free prefixes commonly used by robocallers + sales.
# Not blocked outright — flagged for caution.
TOLLFREE_PREFIXES = {"800", "833", "844", "855", "866", "877", "888"}

# Known scam area codes per FTC + FCC reports (caller ID spoofed origin).
HIGH_RISK_AREA_CODES = {
    "242",  # Bahamas one-ring
    "246",  # Barbados one-ring
    "284",  # British Virgin Islands
    "473",  # Grenada
    "649",  # Turks and Caicos
    "664",  # Montserrat
    "767",  # Dominica
    "809", "829", "849",  # Dominican Republic
    "876",  # Jamaica
}


def _digits_only(phone: str) -> str:
    return "".join(c for c in phone if c.isdigit())


def check(phone: str, customer_area_code: str | None = None) -> tuple[bool, str | None, float]:
    """
    Returns (is_spam, reason, confidence 0-1). Caller decides threshold.
    """
    d = _digits_only(phone)

    # Strip leading country code for US numbers.
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]

    if len(d) != 10:
        return True, "invalid_length", 0.95

    area = d[:3]
    exchange = d[3:6]
    line = d[6:]

    if area + exchange in RESERVED_PREFIXES:
        return True, "reserved_test_number", 1.0

    if area in HIGH_RISK_AREA_CODES:
        return True, f"high_risk_area_code_{area}", 0.85

    if line == "0000" or line == "1234":
        return True, "sequential_line_digits", 0.8

    if len(set(d)) <= 2:
        return True, "repeating_digits", 0.9

    # Neighbor-spoofing: caller's first 6 digits exactly match the customer's.
    # Real neighbors don't all coordinate to call you — robocallers do this
    # because people pick up calls from their own area + exchange.
    if customer_area_code:
        cust = _digits_only(customer_area_code)
        if len(cust) == 11 and cust.startswith("1"):
            cust = cust[1:]
        if len(cust) >= 6 and d[:6] == cust[:6]:
            return True, "neighbor_spoofing", 0.75

    if area in TOLLFREE_PREFIXES:
        return False, "tollfree_caution", 0.4

    return False, None, 0.0
