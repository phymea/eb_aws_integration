# Use official Python base image
FROM python:3.9-slim

# Install system dependencies for opencv
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the main script
COPY main.py ./

# Set environment variable for AWS region (optional, can be overridden)
ENV AWS_DEFAULT_REGION=eu-north-1

# Set entrypoint to allow passing all arguments from docker run
ENTRYPOINT ["python", "main.py"]
