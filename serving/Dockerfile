# Vertex AI custom container: CPU only, no PyTorch (models are ONNX), weights baked in (about 225 MB).
# Build without local Docker:  gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/REPO/serving:v3 .
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# rapidocr pulls in the full opencv-python, which needs GUI libraries this image lacks (libxcb): swap in the headless build
RUN pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless \
 && pip install --no-cache-dir --no-deps opencv-python-headless \
 && python -c "import cv2; print('cv2', cv2.__version__)"
COPY app.py vision.py audio.py identify.py ./
COPY models ./models
ENV AIP_HTTP_PORT=8080 NUMBA_CACHE_DIR=/tmp/numba ORT_THREADS=2
EXPOSE 8080
CMD ["python", "app.py"]
