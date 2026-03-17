FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (curl for API fallbacks, Node.js for AIS proxy)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js dependencies (AIS WebSocket proxy)
COPY package*.json ./
RUN npm install --production 2>/dev/null || true

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create a non-root user for security
RUN adduser --system --uid 1001 backenduser \
    && chown -R backenduser /app

# Switch to the non-root user
USER backenduser

# Expose port
EXPOSE 8000

# Start FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
