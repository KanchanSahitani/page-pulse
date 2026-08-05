FROM python:3.12-slim

# Prevent .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port Render uses by default
EXPOSE 10000

# Run with uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "10000"]
