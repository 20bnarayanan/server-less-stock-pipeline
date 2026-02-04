resource "aws_dynamodb_table" "daily_mover" {
  name         = "daily-stock-mover"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "date"

  attribute {
    name = "date"
    type = "S"
  }

  tags = {
    Project = "stocks-mover"
  }
}
resource "aws_dynamodb_table" "watchlist_daily" {
  name         = "watchlist-daily"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "ticker"
  range_key = "date"

  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "date"
    type = "S"
  }

  tags = {
    Project = "stocks-mover"
  }
}
