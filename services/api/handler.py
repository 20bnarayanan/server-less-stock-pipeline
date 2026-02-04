import os
import json
import boto3
from decimal import Decimal

TABLE_NAME = os.environ["TABLE_NAME"]
DAYS = int(os.environ.get("DAYS", "30"))

ddb = boto3.resource("dynamodb")
table = ddb.Table(TABLE_NAME)


def _json_default(x):
    if isinstance(x, Decimal):
        return float(x)
    raise TypeError


def lambda_handler(event, context):
    # Scan entire table (fine for small scale). Then sort + return last N.
    items = []
    kwargs = {}

    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    # date is ISO YYYY-MM-DD, so string sort works
    items.sort(key=lambda x: x.get("date", ""), reverse=True)
    items = items[:DAYS]

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps({"days": DAYS, "items": items}, default=_json_default),
    }
