FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Create logs directory
RUN mkdir -p logs/fallback

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV FLASK_DEBUG=False
ENV PORT=8080

# Expose port
EXPOSE 8080

# Run with gunicorn (production WSGI server)
CMD exec gunicorn --bind :$PORT --workers 1 --threads 2 --timeout 120 "src.main:create_app()"
