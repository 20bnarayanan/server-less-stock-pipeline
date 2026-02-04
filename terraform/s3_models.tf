resource "aws_s3_bucket" "model_artifacts" {
  bucket_prefix = "stocks-model-artifacts-"
}

output "model_bucket_name" {
  value = aws_s3_bucket.model_artifacts.bucket
}
