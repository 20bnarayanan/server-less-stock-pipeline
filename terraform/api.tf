# ----------------------------
# API Lambda: logs + zip + function
# ----------------------------
resource "aws_cloudwatch_log_group" "api_logs" {
  name              = "/aws/lambda/stocks-mover-api"
  retention_in_days = 14
}

data "archive_file" "api_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../services/api"
  output_path = "${path.module}/../build/api.zip"
}

resource "aws_iam_role" "api_lambda_role" {
  name               = "stocks-mover-api-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "api_basic_logs" {
  role       = aws_iam_role.api_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "api_dynamodb_policy_doc" {
  statement {
    actions = [
      "dynamodb:Scan",
      "dynamodb:Query",
      "dynamodb:GetItem"
    ]
    resources = [aws_dynamodb_table.daily_mover.arn]
  }
}

resource "aws_iam_policy" "api_dynamodb_policy" {
  name   = "stocks-mover-api-ddb"
  policy = data.aws_iam_policy_document.api_dynamodb_policy_doc.json
}

resource "aws_iam_role_policy_attachment" "api_ddb_attach" {
  role       = aws_iam_role.api_lambda_role.name
  policy_arn = aws_iam_policy.api_dynamodb_policy.arn
}

resource "aws_lambda_function" "api" {
  function_name = "stocks-mover-api"
  role          = aws_iam_role.api_lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.11"

  filename         = data.archive_file.api_zip.output_path
  source_code_hash = data.archive_file.api_zip.output_base64sha256

  timeout     = 10
  memory_size = 256

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.daily_mover.name
      DAYS       = "30"
    }
  }

  depends_on = [aws_cloudwatch_log_group.api_logs]
}

# ----------------------------
# API Gateway REST API: GET /movers
# ----------------------------
resource "aws_api_gateway_rest_api" "stocks_api" {
  name = "stocks-mover-api"
}

resource "aws_api_gateway_resource" "movers" {
  rest_api_id = aws_api_gateway_rest_api.stocks_api.id
  parent_id   = aws_api_gateway_rest_api.stocks_api.root_resource_id
  path_part   = "movers"
}

resource "aws_api_gateway_method" "get_movers" {
  rest_api_id   = aws_api_gateway_rest_api.stocks_api.id
  resource_id   = aws_api_gateway_resource.movers.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "get_movers_integration" {
  rest_api_id             = aws_api_gateway_rest_api.stocks_api.id
  resource_id             = aws_api_gateway_resource.movers.id
  http_method             = aws_api_gateway_method.get_movers.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

# CORS preflight: OPTIONS /movers
resource "aws_api_gateway_method" "options_movers" {
  rest_api_id   = aws_api_gateway_rest_api.stocks_api.id
  resource_id   = aws_api_gateway_resource.movers.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options_movers_integration" {
  rest_api_id = aws_api_gateway_rest_api.stocks_api.id
  resource_id = aws_api_gateway_resource.movers.id
  http_method = aws_api_gateway_method.options_movers.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options_movers_response" {
  rest_api_id = aws_api_gateway_rest_api.stocks_api.id
  resource_id = aws_api_gateway_resource.movers.id
  http_method = aws_api_gateway_method.options_movers.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Headers" = true
  }
}

resource "aws_api_gateway_integration_response" "options_movers_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.stocks_api.id
  resource_id = aws_api_gateway_resource.movers.id
  http_method = aws_api_gateway_method.options_movers.http_method
  status_code = aws_api_gateway_method_response.options_movers_response.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type'"
  }

  depends_on = [aws_api_gateway_integration.options_movers_integration]
}

# Allow API Gateway to invoke the API Lambda
resource "aws_lambda_permission" "allow_apigw_invoke_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.stocks_api.execution_arn}/*/*"
}

# Deploy API
resource "aws_api_gateway_deployment" "stocks_api_deploy" {
  rest_api_id = aws_api_gateway_rest_api.stocks_api.id

  triggers = {
    redeploy = sha1(jsonencode([
      aws_api_gateway_integration.get_movers_integration.id,
      aws_api_gateway_integration.predict_integration.id
    ]))
  }

  depends_on = [
    aws_api_gateway_integration.get_movers_integration,
    aws_api_gateway_integration.predict_integration,
    aws_api_gateway_integration_response.options_movers_integration_response
  ]

  lifecycle {
    create_before_destroy = true
  }
}




resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.stocks_api.id
  deployment_id = aws_api_gateway_deployment.stocks_api_deploy.id
  stage_name    = "prod"
}

output "movers_endpoint" {
  value = "${aws_api_gateway_stage.prod.invoke_url}/movers"
}

# /predict resource
resource "aws_api_gateway_resource" "predict" {
  rest_api_id = aws_api_gateway_rest_api.stocks_api.id
  parent_id   = aws_api_gateway_rest_api.stocks_api.root_resource_id
  path_part   = "predict"
}

resource "aws_api_gateway_method" "predict_get" {
  rest_api_id   = aws_api_gateway_rest_api.stocks_api.id
  resource_id   = aws_api_gateway_resource.predict.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "predict_integration" {
  rest_api_id             = aws_api_gateway_rest_api.stocks_api.id
  resource_id             = aws_api_gateway_resource.predict.id
  http_method             = aws_api_gateway_method.predict_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.predict.invoke_arn
}

resource "aws_lambda_permission" "apigw_invoke_predict" {
  statement_id  = "AllowAPIGatewayInvokePredict"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.predict.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.stocks_api.execution_arn}/*/*"
}

