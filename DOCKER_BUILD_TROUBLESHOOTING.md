<<<<<<< HEAD
# Docker Build Troubleshooting Guide

## Common Issues and Solutions

### Issue: `ModuleNotFoundError: No module named 'aiohttp'`

Even though `aiohttp==3.9.1` is in `requirements.txt`, you might encounter this error. Here are the most common causes and solutions:

---

## 🔧 **Solution 1: Clear Docker Build Cache**

**Problem**: Docker is using cached layers from a previous build where requirements.txt was different.

**Solution**:
```bash
# Rebuild without cache
docker-compose build --no-cache api bias-detector

# Or for a specific service
docker-compose build --no-cache api
```

---

## 🔧 **Solution 2: Verify requirements.txt is Copied**

**Problem**: The requirements.txt file might not be in the build context.

**Solution**:
```bash
# Ensure you're in the project root directory
cd /path/to/data-warehouse-app

# Verify requirements.txt exists
ls -la requirements.txt

# Check if it contains aiohttp
grep aiohttp requirements.txt
```

---

## 🔧 **Solution 3: Check Python Version Compatibility**

**Problem**: aiohttp 3.9.1 might have compatibility issues with the Python version.

**Solution**:
```bash
# The Dockerfile uses Python 3.11
# Verify this matches your system:
docker run --rm python:3.11-slim python --version

# If needed, update the Dockerfile to use a different Python version
# Edit Dockerfile line 1: FROM python:3.11-slim
```

---

## 🔧 **Solution 4: Manual Installation Verification**

**Problem**: Dependencies might be failing to install silently.

**Solution**:
```bash
# Build with verbose output
docker-compose build --progress=plain api

# Or check inside a running container
docker-compose run --rm api pip list | grep aiohttp
docker-compose run --rm api python -c "import aiohttp; print(aiohttp.__version__)"
```

---

## 🔧 **Solution 5: Check for .env File Issues**

**Problem**: Missing .env file might cause build to fail (though this shouldn't affect aiohttp).

**Solution**:
```bash
# Create a minimal .env file if it doesn't exist
touch .env

# Or check if .env is in .dockerignore
cat .dockerignore 2>/dev/null | grep -E "^\.env$"
```

---

## 🔧 **Solution 6: System Dependencies**

**Problem**: aiohttp might need additional system libraries.

**Solution**:
The Dockerfile already includes build tools. If issues persist, try adding:
```dockerfile
RUN apt-get update && apt-get install -y \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*
```

---

## 🔧 **Solution 7: Installation Order**

**Problem**: Some packages might need to be installed in a specific order.

**Solution**:
The updated Dockerfile now upgrades pip, setuptools, and wheel first, which should resolve most dependency conflicts.

---

## 🔧 **Solution 8: Check for Multiple Python Environments**

**Problem**: If running outside Docker, you might be using a different Python environment.

**Solution**:
```bash
# Verify you're using the correct Python
which python
python --version

# Check if aiohttp is installed in your local environment
pip list | grep aiohttp

# If running locally (not in Docker), install dependencies
pip install -r requirements.txt
```

---

## 🔧 **Solution 9: Verify Build Context**

**Problem**: Docker build context might not include requirements.txt.

**Solution**:
```bash
# Ensure you're building from the correct directory
pwd  # Should be: /path/to/data-warehouse-app

# Check docker-compose.yml build context
grep -A 5 "build:" docker-compose.yml

# The build context should be "." (current directory)
```

---

## 🔧 **Solution 10: Check Dockerfile Syntax**

**Problem**: Syntax errors in Dockerfile might cause silent failures.

**Solution**:
```bash
# Validate Dockerfile syntax
docker build --dry-run . 2>&1 | head -20

# Or use hadolint (if installed)
hadolint Dockerfile
```

---

## ✅ **Recommended Build Command**

Use this command to ensure a clean build:

```bash
# Stop and remove existing containers
docker-compose down

# Remove old images (optional, but recommended)
docker-compose rm -f

# Rebuild without cache
docker-compose build --no-cache

# Start services
docker-compose up -d

# Check logs for any errors
docker-compose logs api | grep -i error
docker-compose logs bias-detector | grep -i error
```

---

## 🔍 **Debugging Steps**

1. **Check if aiohttp is in requirements.txt**:
   ```bash
   grep -n aiohttp requirements.txt
   ```

2. **Verify the package installs correctly**:
   ```bash
   docker-compose run --rm api pip install aiohttp==3.9.1
   ```

3. **Check installed packages in container**:
   ```bash
   docker-compose run --rm api pip list
   ```

4. **Test import in container**:
   ```bash
   docker-compose run --rm api python -c "import aiohttp; print('SUCCESS')"
   ```

5. **Check build logs**:
   ```bash
   docker-compose build api 2>&1 | tee build.log
   grep -i "aiohttp\|error\|failed" build.log
   ```

---

## 📝 **Updated Dockerfile Features**

The Dockerfile has been updated with:
- ✅ Verification step to ensure aiohttp is installed during build
- ✅ Upgraded pip, setuptools, and wheel before installing requirements
- ✅ Removed .env file requirement (handled by docker-compose at runtime)
- ✅ Better error detection during build

---

## 🆘 **If All Else Fails**

1. **Share the complete build output**:
   ```bash
   docker-compose build --no-cache api > build_output.txt 2>&1
   ```

2. **Check Docker and Docker Compose versions**:
   ```bash
   docker --version
   docker-compose --version
   ```

3. **Verify system resources**:
   ```bash
   docker system df
   docker system prune  # If disk space is low
   ```

4. **Try building manually**:
   ```bash
   docker build -t data-warehouse-test .
   docker run --rm data-warehouse-test python -c "import aiohttp; print('OK')"
   ```

---

## 📞 **Information to Share When Reporting Issues**

If the problem persists, please share:
- Complete build output (`docker-compose build --no-cache api`)
- Docker version (`docker --version`)
- Docker Compose version (`docker-compose --version`)
- Operating system and version
- Contents of `requirements.txt` (to verify aiohttp is there)
- Any error messages from container logs (`docker-compose logs api`)

=======
# Docker Build Troubleshooting Guide

## Common Issues and Solutions

### Issue: `ModuleNotFoundError: No module named 'aiohttp'`

Even though `aiohttp==3.9.1` is in `requirements.txt`, you might encounter this error. Here are the most common causes and solutions:

---

## 🔧 **Solution 1: Clear Docker Build Cache**

**Problem**: Docker is using cached layers from a previous build where requirements.txt was different.

**Solution**:
```bash
# Rebuild without cache
docker-compose build --no-cache api bias-detector

# Or for a specific service
docker-compose build --no-cache api
```

---

## 🔧 **Solution 2: Verify requirements.txt is Copied**

**Problem**: The requirements.txt file might not be in the build context.

**Solution**:
```bash
# Ensure you're in the project root directory
cd /path/to/data-warehouse-app

# Verify requirements.txt exists
ls -la requirements.txt

# Check if it contains aiohttp
grep aiohttp requirements.txt
```

---

## 🔧 **Solution 3: Check Python Version Compatibility**

**Problem**: aiohttp 3.9.1 might have compatibility issues with the Python version.

**Solution**:
```bash
# The Dockerfile uses Python 3.11
# Verify this matches your system:
docker run --rm python:3.11-slim python --version

# If needed, update the Dockerfile to use a different Python version
# Edit Dockerfile line 1: FROM python:3.11-slim
```

---

## 🔧 **Solution 4: Manual Installation Verification**

**Problem**: Dependencies might be failing to install silently.

**Solution**:
```bash
# Build with verbose output
docker-compose build --progress=plain api

# Or check inside a running container
docker-compose run --rm api pip list | grep aiohttp
docker-compose run --rm api python -c "import aiohttp; print(aiohttp.__version__)"
```

---

## 🔧 **Solution 5: Check for .env File Issues**

**Problem**: Missing .env file might cause build to fail (though this shouldn't affect aiohttp).

**Solution**:
```bash
# Create a minimal .env file if it doesn't exist
touch .env

# Or check if .env is in .dockerignore
cat .dockerignore 2>/dev/null | grep -E "^\.env$"
```

---

## 🔧 **Solution 6: System Dependencies**

**Problem**: aiohttp might need additional system libraries.

**Solution**:
The Dockerfile already includes build tools. If issues persist, try adding:
```dockerfile
RUN apt-get update && apt-get install -y \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*
```

---

## 🔧 **Solution 7: Installation Order**

**Problem**: Some packages might need to be installed in a specific order.

**Solution**:
The updated Dockerfile now upgrades pip, setuptools, and wheel first, which should resolve most dependency conflicts.

---

## 🔧 **Solution 8: Check for Multiple Python Environments**

**Problem**: If running outside Docker, you might be using a different Python environment.

**Solution**:
```bash
# Verify you're using the correct Python
which python
python --version

# Check if aiohttp is installed in your local environment
pip list | grep aiohttp

# If running locally (not in Docker), install dependencies
pip install -r requirements.txt
```

---

## 🔧 **Solution 9: Verify Build Context**

**Problem**: Docker build context might not include requirements.txt.

**Solution**:
```bash
# Ensure you're building from the correct directory
pwd  # Should be: /path/to/data-warehouse-app

# Check docker-compose.yml build context
grep -A 5 "build:" docker-compose.yml

# The build context should be "." (current directory)
```

---

## 🔧 **Solution 10: Check Dockerfile Syntax**

**Problem**: Syntax errors in Dockerfile might cause silent failures.

**Solution**:
```bash
# Validate Dockerfile syntax
docker build --dry-run . 2>&1 | head -20

# Or use hadolint (if installed)
hadolint Dockerfile
```

---

## ✅ **Recommended Build Command**

Use this command to ensure a clean build:

```bash
# Stop and remove existing containers
docker-compose down

# Remove old images (optional, but recommended)
docker-compose rm -f

# Rebuild without cache
docker-compose build --no-cache

# Start services
docker-compose up -d

# Check logs for any errors
docker-compose logs api | grep -i error
docker-compose logs bias-detector | grep -i error
```

---

## 🔍 **Debugging Steps**

1. **Check if aiohttp is in requirements.txt**:
   ```bash
   grep -n aiohttp requirements.txt
   ```

2. **Verify the package installs correctly**:
   ```bash
   docker-compose run --rm api pip install aiohttp==3.9.1
   ```

3. **Check installed packages in container**:
   ```bash
   docker-compose run --rm api pip list
   ```

4. **Test import in container**:
   ```bash
   docker-compose run --rm api python -c "import aiohttp; print('SUCCESS')"
   ```

5. **Check build logs**:
   ```bash
   docker-compose build api 2>&1 | tee build.log
   grep -i "aiohttp\|error\|failed" build.log
   ```

---

## 📝 **Updated Dockerfile Features**

The Dockerfile has been updated with:
- ✅ Verification step to ensure aiohttp is installed during build
- ✅ Upgraded pip, setuptools, and wheel before installing requirements
- ✅ Removed .env file requirement (handled by docker-compose at runtime)
- ✅ Better error detection during build

---

## 🆘 **If All Else Fails**

1. **Share the complete build output**:
   ```bash
   docker-compose build --no-cache api > build_output.txt 2>&1
   ```

2. **Check Docker and Docker Compose versions**:
   ```bash
   docker --version
   docker-compose --version
   ```

3. **Verify system resources**:
   ```bash
   docker system df
   docker system prune  # If disk space is low
   ```

4. **Try building manually**:
   ```bash
   docker build -t data-warehouse-test .
   docker run --rm data-warehouse-test python -c "import aiohttp; print('OK')"
   ```

---

## 📞 **Information to Share When Reporting Issues**

If the problem persists, please share:
- Complete build output (`docker-compose build --no-cache api`)
- Docker version (`docker --version`)
- Docker Compose version (`docker-compose --version`)
- Operating system and version
- Contents of `requirements.txt` (to verify aiohttp is there)
- Any error messages from container logs (`docker-compose logs api`)

>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
