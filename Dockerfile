FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    nginx \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY templates/ templates/
COPY static/ static/
COPY nginx.conf /etc/nginx/sites-available/snap-drop
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create upload directory
RUN mkdir -p /app/uploads

# Set permissions
RUN chown -R www-data:www-data /app/uploads
RUN chmod -R 755 /app/uploads

EXPOSE 80

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]