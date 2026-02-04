import os
import json
import math
import datetime as dt
from decimal import Decimal

import boto3
import pandas as pd
import numpy as np
import joblib
from boto3.dynamodb.conditions import Key

# ----------------------------
# Config (env vars)
# ----------------------------
WATCHLIST = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]

WATCHLIST_TABLE_NAME = os.environ["WATCHLIST_TABLE_NAME"]

MODEL_BUCKET = os.environ["MODEL_BUCKET"]
MODEL_KEY = os.environ.get("MODEL_KEY", "rf_shared/model.joblib")
FEATURES_KEY = os.environ.get("FEATURES_KEY", "rf_shared/feature_cols.json")

LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "60"))
MIN_HISTORY_DAYS = int(os.environ.get("MIN_HISTORY_DAYS", "25"))

# Cache model artifacts in /tmp to avoid re-downloading every invoke
LOCAL_MODEL_PATH = "/tmp/model.joblib"
LOCAL_FEATURES_PATH = "/tmp/feature_cols.json"

ddb = boto3.resource("dynamodb")
watchlist_table = ddb.Table(WATCHLIST_TABLE_NAME)

s3 = boto3.client("s3")

# ----------------------------
# Utilities
# ----------------------------
def _iso_to_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)

def _date_to_iso(d: dt.date) -> str:
    return d.isoformat()

def _load_model_and_features():
    # Download once per warm container
    if not os.path.exists(LOCAL_MODEL_PATH):
        s3.download_file(MODEL_BUCKET, MODEL_KEY, LOCAL_MODEL_PATH)

    if not os.path.exists(LOCAL_FEATURES_PATH):
        s3.download_file(MODEL_BUCKET, FEATURES_KEY, LOCAL_FEATURES_PATH)

    model = joblib.load(LOCAL_MODEL_PATH)
    with open(LOCAL_FEATURES_PATH, "r") as f:
        feature_cols = json.load(f)

    return model, feature_cols

def _query_ticker_history(ticker: str, start_iso: str) -> pd.DataFrame:
    """
    Table design: PK=ticker (S), SK=date (S, ISO)
    """
    resp = watchlist_table.query(
        KeyConditionExpression=Key("ticker").eq(ticker) & Key("date").gte(start_iso),
        ScanIndexForward=True,  # ascending dates
    )
    items = resp.get("Items", [])
    if not items:
        return pd.DataFrame()

    # DynamoDB Decimals -> float
    def dec(x):
        if x is None:
            return np.nan
        if isinstance(x, Decimal):
            return float(x)
        return float(x)

    rows = []
    for it in items:
        rows.append(
            {
                "date": it["date"],
                "open": dec(it.get("open")),
                "high": dec(it.get("high")),
                "low": dec(it.get("low")),
                "close": dec(it.get("close")),
                "volume": dec(it.get("volume")),
                "vwap": dec(it.get("vwap")),
            }
        )

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["ticker"] = ticker
    return df

# ----------------------------
# Feature engineering (must match training)
# ----------------------------
def add_ticker_onehots(df: pd.DataFrame) -> pd.DataFrame:
    # Ensure df has 'ticker'
    df = df.copy()
    for t in WATCHLIST:
        df[f"ticker_{t}"] = (df["ticker"] == t).astype(int)
    return df

def add_features_lightweight(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").copy()

    # If high/low missing for some rows, daily_range will be nan; OK.
    df["return_1d"] = df["close"].pct_change(1)
    df["return_5d"] = df["close"].pct_change(5)
    df["return_10d"] = df["close"].pct_change(10)

    df["ma_5"] = df["close"].rolling(5).mean()
    df["ma_20"] = df["close"].rolling(20).mean()
    df["price_to_ma5"] = df["close"] / df["ma_5"]
    df["price_to_ma20"] = df["close"] / df["ma_20"]

    df["volatility_5d"] = df["close"].pct_change().rolling(5).std()
    df["volatility_10d"] = df["close"].pct_change().rolling(10).std()

    df["volume_ma_20"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_ma_20"]

    # RSI (simple)
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    df["rsi_14"] = 100 - (100 / (1 + rs))

    df["daily_range"] = (df["high"] - df["low"]) / df["open"]

    if "vwap" in df.columns:
        df["close_to_vwap"] = df["close"] / df["vwap"]

    df["day_of_week"] = df["date"].dt.dayofweek

    return df

def _prep_latest_features(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    df_feat = add_features_lightweight(df)
    df_feat = add_ticker_onehots(df_feat)

    # Use last available day
    latest = df_feat.iloc[-1:].copy()

    # Ensure all required columns exist
    for c in feature_cols:
        if c not in latest.columns:
            latest[c] = np.nan

    X = latest[feature_cols].copy()
    return X, df_feat  # return full df_feat for "why"

# ----------------------------
# "Why" (brief, UI-friendly)
# ----------------------------
FRIENDLY = {
    # Momentum
    "return_1d": "short-term momentum",
    "return_5d": "5-day momentum",
    "return_10d": "10-day momentum",

    # Trend
    "price_to_ma5": "price vs 5-day average",
    "price_to_ma20": "price vs 20-day average",

    # Volatility
    "volatility_5d": "recent volatility",
    "volatility_10d": "10-day volatility",
    "daily_range": "intraday price range",

    # Volume
    "volume_ratio": "unusual trading volume",

    # Technical
    "rsi_14": "RSI level",
    "close_to_vwap": "close vs VWAP",

    # Time
    "day_of_week": "day-of-week pattern",
}


def _why_string(model, feature_cols, df_feat):
    """
    Short, UI-friendly explanation based on:
    (feature importance) × (how unusual today's value is).
    """
    import numpy as np

    importances = getattr(model, "feature_importances_", None)
    if importances is None or len(df_feat) < 10:
        return "Based on recent price and volume patterns."

    last = df_feat.iloc[-1]

    scores = []
    for i, c in enumerate(feature_cols):
        # Ignore ticker one-hots and raw OHLC fields
        if c.startswith("ticker_"):
            continue
        if c in {"open", "high", "low", "close", "volume", "vwap"}:
            continue
        if c not in df_feat.columns:
            continue

        series = df_feat[c].replace([np.inf, -np.inf], np.nan).astype(float)
        if series.isna().all():
            continue

        mu = series.mean()
        sd = series.std()
        if sd == 0 or not np.isfinite(sd):
            continue

        z = (float(last[c]) - mu) / sd if np.isfinite(last[c]) else 0.0
        imp = float(importances[i]) if i < len(importances) else 0.0

        scores.append((abs(z) * imp, c, z))

    if not scores:
        return "Based on recent price and volume patterns."

    scores.sort(reverse=True, key=lambda x: x[0])
    top = scores[:2]

    phrases = []
    for _, c, z in top:
        label = FRIENDLY.get(c, c)
        direction = "high" if z >= 0 else "low"
        phrases.append(f"{direction} {label}")

    if len(phrases) == 1:
        return f"Driven mainly by {phrases[0]}."
    return f"Driven mainly by {phrases[0]} and {phrases[1]}."


# ----------------------------
# Lambda handler
# ----------------------------
def lambda_handler(event, context):
    model, feature_cols = _load_model_and_features()

    # Look back N days from today (UTC). We only need a window.
    start = (dt.date.today() - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()

    preds = []
    for t in WATCHLIST:
        df = _query_ticker_history(t, start)
        if df.empty or len(df) < MIN_HISTORY_DAYS:
            preds.append(
                {
                    "ticker": t,
                    "pred_up": None,
                    "prob_up": None,
                    "why": "Not enough recent history yet.",
                }
            )
            continue

        X_latest, df_feat = _prep_latest_features(df, feature_cols)

        # If any required features are missing today, don't guess.
        if X_latest.isna().any(axis=1).iloc[0]:
            preds.append(
                {
                    "ticker": t,
                    "pred_up": None,
                    "prob_up": None,
                    "why": "Missing feature values for today.",
                }
            )
            continue

        prob_up = float(model.predict_proba(X_latest)[0, 1])
        pred_up = bool(prob_up >= 0.5)
        why = _why_string(model, feature_cols, df_feat)

        preds.append(
            {
                "ticker": t,
                "pred_up": pred_up,
                "prob_up": prob_up,
                "why": why,
            }
        )

    body = {"asof": dt.datetime.utcnow().isoformat() + "Z", "predictions": preds}

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }
