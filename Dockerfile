# Use a lightweight, multi-stage build for a smaller final image.
# Stage 1: Build stage with build-essential for potential C dependencies
FROM python:3.11-slim-bookworm as builder

WORKDIR /usr/src/app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Final runtime stage
FROM python:3.11-slim-bookworm

LABEL maintainer="Your Name <your-email@example.com>"
LABEL description="A Discord bot to parse chat logs with Gemini and create Google Calendar events."

WORKDIR /usr/src/app

# Create a non-root user for security
RUN useradd -m -s /bin/bash appuser
USER appuser

# Copy installed dependencies from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Command to run the bot
CMD ["python", "main.py"]
