data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingest_lambda_role" {
  name               = "stocks-mover-ingest-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ingest_basic_logs" {
  role       = aws_iam_role.ingest_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "ingest_dynamodb_policy_doc" {
  statement {
    actions = [
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:BatchWriteItem"
    ]
    resources = [
      aws_dynamodb_table.daily_mover.arn,
      aws_dynamodb_table.watchlist_daily.arn
    ]
  }
}

resource "aws_iam_policy" "ingest_dynamodb_policy" {
  name   = "stocks-mover-ingest-ddb"
  policy = data.aws_iam_policy_document.ingest_dynamodb_policy_doc.json
}

resource "aws_iam_role_policy_attachment" "ingest_ddb_attach" {
  role       = aws_iam_role.ingest_lambda_role.name
  policy_arn = aws_iam_policy.ingest_dynamodb_policy.arn
}

# --- Predict Lambda role ---
resource "aws_iam_role" "predict_lambda_role" {
  name               = "stocks-mover-predict-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "predict_basic_logs" {
  role       = aws_iam_role.predict_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB: Query watchlist-daily
data "aws_iam_policy_document" "predict_dynamodb_policy_doc" {
  statement {
    actions = [
      "dynamodb:Query",
      "dynamodb:GetItem"
    ]
    resources = [
      aws_dynamodb_table.watchlist_daily.arn
    ]
  }
}

resource "aws_iam_policy" "predict_dynamodb_policy" {
  name   = "stocks-mover-predict-ddb"
  policy = data.aws_iam_policy_document.predict_dynamodb_policy_doc.json
}

resource "aws_iam_role_policy_attachment" "predict_ddb_attach" {
  role       = aws_iam_role.predict_lambda_role.name
  policy_arn = aws_iam_policy.predict_dynamodb_policy.arn
}

# S3: download model + feature json
data "aws_iam_policy_document" "predict_s3_policy_doc" {
  statement {
    actions = [
      "s3:GetObject"
    ]
    resources = [
      "${aws_s3_bucket.model_artifacts.arn}/*"
    ]
  }
}

resource "aws_iam_policy" "predict_s3_policy" {
  name   = "stocks-mover-predict-s3"
  policy = data.aws_iam_policy_document.predict_s3_policy_doc.json
}

resource "aws_iam_role_policy_attachment" "predict_s3_attach" {
  role       = aws_iam_role.predict_lambda_role.name
  policy_arn = aws_iam_policy.predict_s3_policy.arn
}

