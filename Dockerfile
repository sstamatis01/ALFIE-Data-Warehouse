FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including build tools and setuptools for pkg_resources)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    gfortran \
    libblas-dev \
    liblapack-dev \
    python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies.
# Use python -m pip so installs go to the same interpreter that runs the app.
# Reinstall setuptools after other deps (concept-drift consumer needs pkg_resources).
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir -r requirements.txt && \
    python -m pip install --no-cache-dir --force-reinstall "setuptools>=65.0.0"

# Verify critical packages (concept-drift consumer needs pkg_resources; run it in Anaconda or install setuptools if missing)
RUN python -c "import aiohttp; print('aiohttp version:', aiohttp.__version__)" && \
    python -c "import fastapi; import uvicorn; import pandas; import numpy" && \
    echo "All critical packages verified successfully"

# Copy application code
COPY app/ ./app/
COPY kafka_bias_detector_consumer_example.py ./
COPY kafka_automl_consumer_example_v3.py ./
COPY kafka_concept_drift_consumer_example.py ./

# Note: .env is handled via env_file in docker-compose.yml, so it's not required at build time
# If .env exists, it will be copied, but the build won't fail if it doesn't exist
# (docker-compose will inject environment variables at runtime)

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
