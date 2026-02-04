variable "aws_region" {
  type    = string
  default = "us-east-2"
}

variable "massive_api_key" {
  type      = string
  sensitive = true
}

variable "massive_base_url" {
  type    = string
  default = "https://api.massive.com" 
}

variable "predict_image_uri" {
  type = string
}
