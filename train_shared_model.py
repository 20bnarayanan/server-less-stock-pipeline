import os
import json
import datetime as dt

import boto3
import pandas as pd
import numpy as np
import joblib

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

# -----------------------
# Config (edit if needed)
# -----------------------
REGION = os.getenv("AWS_REGION", "us-east-2")
TABLE_NAME = os.getenv("WATCHLIST_TABLE_NAME", "watchlist-daily")
MODEL_BUCKET = os.getenv("MODEL_BUCKET", "stocks-model-artifacts-20260204024951851200000001")
MODEL_PREFIX = os.getenv("MODEL_PREFIX", "rf_shared")

WATCHLIST = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]

# model params (lightweight)
N_ESTIMATORS = 200
MAX_DEPTH = 8
MIN_SAMPLES_SPLIT = 10
MIN_SAMPLES_LEAF = 5
RANDOM_STATE = 42

# -----------------------
# Dynamo helpers
# -----------------------
ddb = boto3.resource("dynamodb", region_name=REGION)
table = ddb.Table(TABLE_NAME)
s3 = boto3.client("s3", region_name=REGION)

def query_all_for_ticker(ticker: str):
    """Pull all rows for ticker (PK=ticker) from DDB."""
    items = []
    kwargs = {
        "KeyConditionExpression": "ticker = :t",
        "ExpressionAttributeValues": {":t": ticker},
    }
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items

def ddb_items_to_df(items, ticker):
    """Convert DDB Items to DataFrame with numeric fields."""
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)
    df["ticker"] = ticker
    df["date"] = pd.to_datetime(df["date"])

    # numeric fields you may have
    for col in ["open", "high", "low", "close", "volume", "vwap"]:
        if col in df.columns:
            df[col] = df[col].astype(float)

    return df.sort_values("date").reset_index(drop=True)

# -----------------------
# Feature engineering (DDB-compatible)
# -----------------------
def add_features(df):
    df = df.sort_values("date").copy()

    # returns
    df["return_1d"] = df["close"].pct_change(1)
    df["return_5d"] = df["close"].pct_change(5)
    df["return_10d"] = df["close"].pct_change(10)

    # moving averages + ratios
    df["ma_5"] = df["close"].rolling(5).mean()
    df["ma_20"] = df["close"].rolling(20).mean()
    df["price_to_ma5"] = df["close"] / df["ma_5"]
    df["price_to_ma20"] = df["close"] / df["ma_20"]

    # volatility
    df["volatility_5d"] = df["close"].pct_change().rolling(5).std()
    df["volatility_10d"] = df["close"].pct_change().rolling(10).std()

    # volume
    df["volume_ma_20"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_ma_20"]

    # RSI-14
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # daily range (only if high/low exist)
    if "high" in df.columns and "low" in df.columns:
        df["daily_range"] = (df["high"] - df["low"]) / df["open"]
    else:
        df["daily_range"] = np.nan

    # close vs vwap (only if vwap exists)
    if "vwap" in df.columns:
        df["close_to_vwap"] = df["close"] / df["vwap"]
    else:
        df["close_to_vwap"] = np.nan

    # day of week
    df["day_of_week"] = df["date"].dt.dayofweek

    return df

def add_target(df):
    df = df.copy()
    df["tomorrow_close"] = df["close"].shift(-1)
    df["target"] = (df["tomorrow_close"] > df["close"]).astype(int)
    return df

# -----------------------
# Build shared dataset
# -----------------------
frames = []
for t in WATCHLIST:
    items = query_all_for_ticker(t)
    df = ddb_items_to_df(items, t)
    if df.empty:
        print(f"SKIP {t}: no data")
        continue
    df = add_features(df)
    df = add_target(df)
    frames.append(df)

all_df = pd.concat(frames, ignore_index=True)

# One-hot ticker for shared model
all_df = pd.get_dummies(all_df, columns=["ticker"], prefix="ticker")

# Feature columns
exclude = {"date", "tomorrow_close", "target"}
feature_cols = [c for c in all_df.columns if c not in exclude]

# Drop rows missing features/target
clean = all_df.dropna(subset=feature_cols + ["target"]).copy()

# Time-based split across whole dataset (by date)
clean = clean.sort_values("date").reset_index(drop=True)
split_idx = int(len(clean) * 0.8)

train = clean.iloc[:split_idx]
test = clean.iloc[split_idx:]

X_train = train[feature_cols]
y_train = train["target"]
X_test = test[feature_cols]
y_test = test["target"]

print(f"Total samples: {len(clean)} | train={len(train)} test={len(test)} | features={len(feature_cols)}")

# -----------------------
# Train model
# -----------------------
model = RandomForestClassifier(
    n_estimators=N_ESTIMATORS,
    max_depth=MAX_DEPTH,
    min_samples_split=MIN_SAMPLES_SPLIT,
    min_samples_leaf=MIN_SAMPLES_LEAF,
    random_state=RANDOM_STATE,
    n_jobs=-1,
    class_weight="balanced",
)
model.fit(X_train, y_train)

pred = model.predict(X_test)
proba = model.predict_proba(X_test)[:, 1]
acc = accuracy_score(y_test, pred)

print(f"Test accuracy: {acc:.3f}")

# -----------------------
# Save artifacts locally
# -----------------------
os.makedirs("artifacts", exist_ok=True)
model_path = "artifacts/model.joblib"
features_path = "artifacts/feature_cols.json"

joblib.dump(model, model_path)
with open(features_path, "w") as f:
    json.dump(feature_cols, f, indent=2)

print("Saved:", model_path, features_path)

# -----------------------
# Upload to S3
# -----------------------
model_key = f"{MODEL_PREFIX}/model.joblib"
features_key = f"{MODEL_PREFIX}/feature_cols.json"

s3.upload_file(model_path, MODEL_BUCKET, model_key)
s3.upload_file(features_path, MODEL_BUCKET, features_key)

print(f"Uploaded to s3://{MODEL_BUCKET}/{MODEL_PREFIX}/")
