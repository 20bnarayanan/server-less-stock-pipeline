resource "aws_ecr_repository" "predict" {
  name = "stocks-mover-predict"
  force_delete = true
}

output "predict_ecr_repo_url" {
  value = aws_ecr_repository.predict.repository_url
}
