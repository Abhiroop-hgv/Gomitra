# Pose + posture service: DeepLabCut SuperAnimal-Quadruped (PyTorch, CPU) with the weights baked in.
# Slow (about 5 s per frame on CPU) and large, so it is its own Cloud Run service, not part of the model container.
FROM python:3.11-slim
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 HF_HOME=/opt/hf TORCH_HOME=/opt/torch PYTHONUNBUFFERED=1
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt
# make sure only the headless OpenCV is present (a GUI build needs libxcb, which this image lacks)
RUN pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless || true \
 && pip install --no-deps opencv-python-headless && python -c "import cv2; print('cv2', cv2.__version__)"
COPY pose_estimation.py activity_monitoring.py app.py warmup.py warmup.jpg ./
# download the pretrained weights into the image now, and show in the build log whether the pipeline works
RUN python warmup.py || echo "WARMUP FAILED (see above)"
ENV PORT=8080
CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT}
