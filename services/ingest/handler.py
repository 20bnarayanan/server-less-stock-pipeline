import os
import time
import random
import datetime as dt
from decimal import Decimal

import boto3
import requests

# ----------------------------
# Config (Lambda env vars)
# ----------------------------
API_KEY = os.environ["MASSIVE_API_KEY"]
BASE_URL = os.environ.get("MASSIVE_BASE_URL", "https://api.massive.com").rstrip("/")
TABLE_NAME = os.environ["TABLE_NAME"]

WATCHLIST = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]

# Optional pacing (not needed for grouped endpoint, but kept for safety)
MIN_GAP_S = float(os.environ.get("MIN_GAP_S", "0"))

SESSION = requests.Session()
RETRYABLE = {429, 500, 502, 503, 504}
_last_call_ts = 0.0

ddb = boto3.resource("dynamodb")
table = ddb.Table(TABLE_NAME)

WATCHLIST_TABLE_NAME = os.environ["WATCHLIST_TABLE_NAME"]
watchlist_table = ddb.Table(WATCHLIST_TABLE_NAME)

# ----------------------------
# Helpers
# ----------------------------
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

def previous_trading_day(reference_dt=None) -> dt.date:
    """
    Returns the last fully-closed US trading day based on New York time.
    If it's a weekday, returns the prior weekday (Mon->Fri).
    If it's Sat/Sun, returns prior Fri.
    """
    if reference_dt is None:
        reference_dt = dt.datetime.now(NY)
    else:
        # if a datetime is passed, normalize to NY
        if isinstance(reference_dt, dt.date) and not isinstance(reference_dt, dt.datetime):
            reference_dt = dt.datetime.combine(reference_dt, dt.time(12, 0), tzinfo=NY)
        else:
            reference_dt = reference_dt.astimezone(NY)

    today_ny = reference_dt.date()
    wd = today_ny.weekday()  # Mon=0 ... Sun=6

    if wd == 0:  # Monday -> previous Friday
        return today_ny - dt.timedelta(days=3)
    if wd == 6:  # Sunday -> Friday
        return today_ny - dt.timedelta(days=2)
    if wd == 5:  # Saturday -> Friday
        return today_ny - dt.timedelta(days=1)
    # Tue–Fri -> yesterday
    return today_ny - dt.timedelta(days=1)



def _pace(min_gap_s=MIN_GAP_S):
    global _last_call_ts
    if min_gap_s <= 0:
        return
    now = time.time()
    wait = min_gap_s - (now - _last_call_ts)
    if wait > 0:
        time.sleep(wait)
    _last_call_ts = time.time()


def get_json(url, params, attempts=4):
    last_status = None
    last_body = None

    for i in range(attempts):
        _pace()

        r = SESSION.get(url, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()

        last_status = r.status_code
        last_body = r.text[:500] if r.text else None

        if r.status_code in RETRYABLE:
            ra = r.headers.get("Retry-After")
            try:
                sleep_s = float(ra) if ra else (2 ** i)
            except ValueError:
                sleep_s = (2 ** i)

            time.sleep(min(sleep_s + random.uniform(0, 0.5), 30))
            continue

        # non-retryable
        r.raise_for_status()

    raise RuntimeError(f"{last_status} after {attempts} attempts: {url} body={last_body}")


def fetch_grouped_daily(date_iso: str):
    """
    One request returns all tickers for the day.
    Expected keys per row: T (ticker), o (open), c (close), v (volume)
    """
    url = f"{BASE_URL}/v2/aggs/grouped/locale/us/market/stocks/{date_iso}"
    data = get_json(url, {"apiKey": API_KEY, "adjusted": "true"})

    results = data.get("results") or []
    if not results:
        return []

    rows = []
    for r in results:
        t = r.get("T")
        o = r.get("o")
        c = r.get("c")
        v = r.get("v")
        h = r.get("h")
        l = r.get("l")
        vw = r.get("vw")
        if not t or o is None or c is None:
            continue
        rows.append(
            {
                "ticker": str(t),
                "open": float(o),
                "close": float(c),
                "high": float(h) if h is not None else None,
                "low": float(l) if l is not None else None,
                "vwap": float(vw) if vw is not None else None,
                "volume": float(v)if v is not None else 0.0,
            }
        )
    return rows


def pick_biggest_mover(rows):
    wl = [x for x in rows if x["ticker"] in WATCHLIST]
    if not wl:
        raise RuntimeError("No watchlist tickers found in grouped response.")

    best = None
    for x in wl:
        open_p = x["open"]
        close_p = x["close"]

        if open_p == 0:
            continue

        pct = ((close_p - open_p) / open_p) * 100.0
        abs_pct = abs(pct)

        if best is None or abs_pct > best["abs_change"]:
            best = {
                "ticker": x["ticker"],
                "open": open_p,
                "close": close_p,
                "percent_change": pct,
                "abs_change": abs_pct,
            }

    if best is None:
        raise RuntimeError("Could not compute winner (open prices were zero or missing).")

    return best


def write_winner_to_ddb(date_iso: str, winner: dict):
    """
    Writes a single row per date.
    Uses a condition to avoid overwriting if the item already exists.
    """
    from botocore.exceptions import ClientError
    item = {
        "date": date_iso,
        "ticker": winner["ticker"],
        "percent_change": Decimal(str(round(winner["percent_change"], 6))),
        "close": Decimal(str(round(winner["close"], 6))),
    }

    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(#d)",
            ExpressionAttributeNames={"#d": "date"},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            # already exists; keep it and continue
            return item
        raise
    return item

def write_watchlist_ohlcv(date_iso: str, rows: list):
    """
    Writes one row per watchlist ticker per day.
    PK = ticker, SK = date
    """
    wl = [r for r in rows if r["ticker"] in WATCHLIST]
    if not wl:
        raise RuntimeError("No watchlist tickers found in grouped response.")

    with watchlist_table.batch_writer() as bw:
        for r in wl:
            item = {
                "ticker": r["ticker"],
                "date": date_iso,
                "open": Decimal(str(round(r["open"], 6))),
                "close": Decimal(str(round(r["close"], 6))),
                "volume": Decimal(str(round(r["volume"], 6))),
            }

            # optional fields if present
            if r.get("high") is not None:
                item["high"] = Decimal(str(round(r["high"], 6)))
            if r.get("low") is not None:
                item["low"] = Decimal(str(round(r["low"], 6)))
            if r.get("vwap") is not None:
                item["vwap"] = Decimal(str(round(r["vwap"], 6)))

            bw.put_item(Item=item)


# ----------------------------
# Lambda entry
# ----------------------------
def lambda_handler(event, context):
    """
    Always ingest the last fully-closed trading day.
    Ignore any 'date' passed in events (prevents accidental 'today' or bad overrides).
    """
    # Always use yesterday/prev weekday
    date_iso = previous_trading_day().isoformat()

    # Debug
    print("BASE_URL=", BASE_URL)
    print("API_KEY_LAST4=", API_KEY[-4:])
    print("FORCED_DATE=", date_iso)
    print("RAW_EVENT=", event)

    rows = fetch_grouped_daily(date_iso)
    if not rows:
        raise RuntimeError(f"No grouped daily data returned for {date_iso}.")

    write_watchlist_ohlcv(date_iso, rows)

    winner = pick_biggest_mover(rows)
    saved_item = write_winner_to_ddb(date_iso, winner)

    return {
        "ok": True,
        "date": date_iso,
        "winner": {
            "ticker": winner["ticker"],
            "percent_change": float(saved_item["percent_change"]),
            "close": float(saved_item["close"]),
        },
        "ddb_item": saved_item,
    }

