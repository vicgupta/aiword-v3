# Start with a Python base image
FROM python:3.12-slim

# Set working directory for the backend
WORKDIR /tmp/news

# Install system dependencies: Nginx and Supervisor
RUN apt-get update && apt-get install -y nginx supervisor

# Copy backend code and install Python dependencies
COPY . .
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" sqlmodel apscheduler pytz gunicorn python-dotenv

COPY ./nginx.conf /etc/nginx/nginx.conf
COPY ./supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose port 80, which is what Nginx will be listening on
EXPOSE 80

# The main command to run when the container starts
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]