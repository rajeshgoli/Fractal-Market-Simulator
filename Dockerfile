# Stage 1: Build React frontend
FROM node:20 AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python + static
FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/

# Copy demo data file (trimmed from 2019 onwards for smaller memory footprint)
COPY test_data/es-30m-demo.csv test_data/es-30m.csv

# Copy React build from frontend stage
COPY --from=frontend /app/frontend/dist static/

# Expose port
EXPOSE 8000

# Run the server
CMD ["python", "-m", "src.replay_server.main", "--data-dir", "/app/test_data", "--host", "0.0.0.0"]
