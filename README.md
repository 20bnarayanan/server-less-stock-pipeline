# Stocks Serverless Pipeline

A fully serverless AWS data pipeline that tracks the daily top-moving stock from a fixed tech watchlist, stores results in DynamoDB, exposes them through a REST API, and displays the data on a public dashboard.  
The system also includes an ML-based prediction endpoint that forecasts next-day price direction for each stock.

---

## Overview

Each weekday, the system automatically ingests market data (Massive API), computes daily movers, persists results, available through a frontend. An additional machine learning model provides directional predictions with confidence scores and explanations.

---

## What the System Does

On each scheduled run, the pipeline:

1. Fetches daily market data for a fixed watchlist:
   - AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA
2. Calculates percent change for each ticker
3. Identifies the single largest mover (up or down)
4. Stores results in DynamoDB
5. Exposes historical data via a REST API
6. Displays results on a public website

The prediction model:
- Generates next-day UP/DOWN predictions for all tickers
- Normalizes probabilities to represent confidence in the predicted direction
- Returns a short explanation describing the primary drivers behind each prediction

---

## Tech Stack

### Backend
- AWS Lambda 
- Amazon EventBridge (scheduled cron trigger)
- Amazon DynamoDB
- Amazon API Gateway (REST)
- Amazon ECR (for ML Lambda container images)
- Terraform (Infrastructure as Code)

### Frontend
- React (Vite)
- AWS S3 Static Website Hosting

---

## Architecture

EventBridge (daily schedule)  
→ Lambda: stocks-mover-ingest  
→ DynamoDB (daily-stock-mover, watchlist-daily)  
→ API Gateway  
→ GET /movers  
→ GET /predict  
→ React Frontend (S3 Static Website)

---

## Repository Structure

- terraform/ — Infrastructure as Code
- services/ — Lambda source code
  - ingest/ — Daily ingestion Lambda
  - movers_api/ — GET /movers Lambda
  - predict/ — ML prediction Lambda (container image)
- frontend/ — React (Vite) frontend
- train_shared_rf.py — Model training script
- docs/ — Architecture diagram and screenshots

---

## API Endpoints

### GET /movers

Returns historical daily top movers.

Example response:

{
  "date": "2026-02-03",
  "ticker": "NVDA",
  "percent_change": -4.12,
  "close_price": 720.33
}

### GET /predict

Returns next-day predictions for all tickers.

Example response:

{
  "predictions": [
    {
      "ticker": "AAPL",
      "pred_up": true,
      "prob_up": 0.61,
      "why": "Driven mainly by high RSI level and strong recent momentum."
    }
  ]
}

---

## Deployment Guide

### Prerequisites
- AWS account
- AWS CLI configured locally
- Terraform installed
- Docker installed (for ML Lambda image)
- Node.js installed (for frontend)

---

### Deploy Infrastructure

From the terraform/ directory:

terraform init  
terraform apply  

This provisions:
- DynamoDB tables
- Lambda functions
- API Gateway
- EventBridge schedule
- IAM roles and policies
- ECR repository for the prediction service

---

### Deploy the Prediction Model

Build and push the container image:

docker build -t stocks-mover-predict .  
docker tag stocks-mover-predict:latest <account-id>.dkr.ecr.<region>.amazonaws.com/stocks-mover-predict:latest  
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/stocks-mover-predict:latest  

Update the Terraform image URI if required and re-apply:

terraform apply  

---

### Automated Ingestion

The ingestion Lambda is triggered automatically on the day after closing via EventBridge. No manual intervention is required.

---

### Run the Frontend Locally (Optional)

From the frontend/ directory:

npm install  
npm run dev  

Create a local environment file:

VITE_API_BASE=https://<api-id>.execute-api.<region>.amazonaws.com/prod

---

### Deploy the Frontend

Build and upload the static site:

npm run build  
aws s3 sync dist s3://<frontend-bucket-name> --delete  

Ensure S3 static website hosting is enabled.

---

## Live Deployment

Frontend:  
http://stock-mover-pc.s3-website.us-east-2.amazonaws.com


---

## Design Decisions and Trade-offs

- Terraform is used for backend infrastructure to ensure reproducibility and clean environment management.
- The ML prediction service is deployed as a Lambda container image because required libraries exceed Lambda layer size limits.
- S3 static hosting was chosen for the frontend to keep deployment simple and cost-effective.
- Prediction probabilities are normalized to represent confidence in the predicted direction rather than raw model outputs.
