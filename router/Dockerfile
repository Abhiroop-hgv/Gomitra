# GoMitra router + web app. No model weights here: models live in the serving container (Vertex AI / Cloud Run).
# Build:  gcloud builds submit --tag asia-south1-docker.pkg.dev/PROJECT/cattle/router:v1 .
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
COPY static ./static
ENV PORT=8080
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
