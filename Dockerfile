# Start with a Python base image
FROM python:3.12-slim

WORKDIR /tmp/news

RUN apt-get update && apt-get install -y nginx supervisor gunicorn

# RUN pip install --no-cache-dir fastapi "uvicorn[standard]" sqlmodel apscheduler pytz gunicorn python-dotenv

RUN cp ./nginx.conf /etc/nginx/nginx.conf
RUN cp ./supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose port 80, which is what Nginx will be listening on
EXPOSE 80

# The main command to run when the container starts
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

# apt-get update && apt-get install -y nginx supervisor gunicorn
# /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf