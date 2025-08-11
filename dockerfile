# ---- Base Stage ----
# Use an Alpine-based Python image. Match the version from requirements.txt (3.12).
FROM python:3.12-alpine AS base

# Set environment variables for python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set the working directory
WORKDIR /app


# ---- Builder Stage ----
# This stage installs dependencies, including build-time requirements
FROM base AS builder

# Install system dependencies needed to build wheels for packages like mysqlclient and cryptography.
# Alpine uses 'apk' and has different package names.
RUN apk add --no-cache \
    build-base \
    mariadb-dev \
    libffi-dev \
    openssl-dev \
    cargo

# Copy only the requirements file to leverage Docker cache
COPY requirements.txt .

# Install python dependencies into a specific directory
# Using a virtual environment inside the builder is a robust pattern
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ---- Final Stage ----
# This is the lean, final image that will be deployed
FROM base AS final

# Copy the installed virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy only the application source code
COPY src/ /app/src/

# Make the venv's python the default
ENV PATH="/opt/venv/bin:$PATH"

# Expose the port the app runs on
EXPOSE 8000

# The command to run the application, using the correct app-dir
# The CMD now uses the python from the venv, ensuring it finds the packages.
CMD ["uvicorn", "bi_agents.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]