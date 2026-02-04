resource "aws_cloudwatch_log_group" "ingest_logs" {
  name              = "/aws/lambda/stocks-mover-ingest"
  retention_in_days = 14
}

data "archive_file" "ingest_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../services/ingest"
  output_path = "${path.module}/../build/ingest.zip"
}

resource "aws_lambda_function" "ingest" {
  function_name = "stocks-mover-ingest"
  role          = aws_iam_role.ingest_lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.11"

  filename         = data.archive_file.ingest_zip.output_path
  source_code_hash = data.archive_file.ingest_zip.output_base64sha256

  timeout     = 30
  memory_size = 256

  environment {
    variables = {
      TABLE_NAME           = aws_dynamodb_table.daily_mover.name
      WATCHLIST_TABLE_NAME = aws_dynamodb_table.watchlist_daily.name
      MASSIVE_API_KEY      = var.massive_api_key
      MASSIVE_BASE_URL     = var.massive_base_url
    }
  }

  depends_on = [aws_cloudwatch_log_group.ingest_logs]
}

resource "aws_cloudwatch_log_group" "predict_logs" {
  name              = "/aws/lambda/stocks-mover-predict"
  retention_in_days = 14
}


resource "aws_lambda_function" "predict" {
  function_name = "stocks-mover-predict"
  role          = aws_iam_role.predict_lambda_role.arn

  package_type = "Image"
  image_uri = "014681966875.dkr.ecr.us-east-2.amazonaws.com/stocks-mover-predict:amd64"


  timeout     = 30
  memory_size = 1024

  environment {
    variables = {
      WATCHLIST_TABLE_NAME = aws_dynamodb_table.watchlist_daily.name
      MODEL_BUCKET         = aws_s3_bucket.model_artifacts.bucket
      MODEL_KEY            = "rf_shared/model.joblib"
      FEATURES_KEY         = "rf_shared/feature_cols.json"
      LOOKBACK_DAYS        = "60"
      MIN_HISTORY_DAYS     = "25"
    }
  }
}
