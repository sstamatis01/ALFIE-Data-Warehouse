FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including build tools for scientific libraries)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    gfortran \
    libblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Verify critical packages are installed (fail build if missing)
RUN python -c "import aiohttp; print('aiohttp version:', aiohttp.__version__)" && \
    python -c "import fastapi; import uvicorn; import pandas; import numpy" && \
    echo "All critical packages verified successfully"

# Copy application code
COPY app/ ./app/
COPY kafka_bias_detector_consumer_example.py ./
COPY kafka_automl_consumer_example.py ./
# Note: automl_predictor.zip is mounted as a volume in docker-compose.yml
# If you want to include it in the image instead, uncomment the line below:
# COPY automl_predictor.zip ./automl_predictor.zip

# Note: .env is handled via env_file in docker-compose.yml, so it's not required at build time
# If .env exists, it will be copied, but the build won't fail if it doesn't exist
# (docker-compose will inject environment variables at runtime)

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
