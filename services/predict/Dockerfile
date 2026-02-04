FROM public.ecr.aws/lambda/python:3.11

# Install Python deps (wheels)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY handler.py ${LAMBDA_TASK_ROOT}/handler.py

CMD ["handler.lambda_handler"]
