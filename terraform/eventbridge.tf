# Weekday schedule to trigger the daily ingest Lambda.
# NOTE: EventBridge cron is in UTC.
# 22:00 UTC runs Mon–Fri at 22:00 UTC.
resource "aws_cloudwatch_event_rule" "daily_ingest" {
  name                = "stocks-mover-daily-ingest"
  description         = "Run stocks mover ingest lambda on weekdays at 22:00 UTC"
  schedule_expression = "cron(0 22 ? * MON-FRI *)"
}

resource "aws_cloudwatch_event_target" "daily_ingest_target" {
  rule      = aws_cloudwatch_event_rule.daily_ingest.name
  target_id = "stocks-mover-ingest"
  arn       = aws_lambda_function.ingest.arn
}

resource "aws_lambda_permission" "allow_eventbridge_invoke_ingest" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_ingest.arn
}
