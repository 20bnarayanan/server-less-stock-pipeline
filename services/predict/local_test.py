import os

# IMPORTANT: do NOT hardcode the key here
# Run with: MASSIVE_API_KEY=... python local_test.py
if "MASSIVE_API_KEY" not in os.environ:
    raise RuntimeError("Set MASSIVE_API_KEY in your environment first.")

os.environ.setdefault("LOCAL_MODE", "1")
os.environ.setdefault("MASSIVE_BASE_URL", "https://api.massive.com")
os.environ.setdefault("PRED_TABLE_NAME", "stock-direction-preds")
os.environ.setdefault("LOOKBACK_TRADING_DAYS", "60")
os.environ.setdefault("MIN_GAP_S", "0.25")

from handler import lambda_handler

print(lambda_handler({"as_of": "2026-02-03"}, None))
