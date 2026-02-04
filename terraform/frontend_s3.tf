resource "aws_s3_bucket" "frontend" {
  bucket = "stock-mover-pc"
}

resource "aws_s3_bucket_ownership_controls" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  index_document {
    suffix = "index.html"
  }

  # React SPA routing fallback
  error_document {
    key = "index.html"
  }
}

data "aws_iam_policy_document" "frontend_public_read" {
  statement {
    sid     = "PublicReadGetObject"
    effect  = "Allow"
    actions = ["s3:GetObject"]

    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_public_read.json

  depends_on = [aws_s3_bucket_public_access_block.frontend]
}

# Upload built React files from ../frontend/dist
locals {
  frontend_dist = "${path.module}/../frontend/dist"
}

resource "aws_s3_object" "frontend_files" {
  for_each = fileset(local.frontend_dist, "**/*")

  bucket = aws_s3_bucket.frontend.id
  key    = each.value
  source = "${local.frontend_dist}/${each.value}"

  etag = filemd5("${local.frontend_dist}/${each.value}")

  content_type = lookup(
    {
      html = "text/html"
      js   = "application/javascript"
      css  = "text/css"
      svg  = "image/svg+xml"
      png  = "image/png"
      jpg  = "image/jpeg"
      jpeg = "image/jpeg"
      ico  = "image/x-icon"
      json = "application/json"
      txt  = "text/plain"
      map  = "application/json"
    },
    element(split(".", each.value), length(split(".", each.value)) - 1),
    "application/octet-stream"
  )

  depends_on = [aws_s3_bucket_website_configuration.frontend]
}

output "frontend_url" {
  value = "http://${aws_s3_bucket.frontend.bucket}.s3-website.${var.aws_region}.amazonaws.com"
}
