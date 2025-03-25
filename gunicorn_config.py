import multiprocessing

# Gunicorn configuration for production deployment

# Bind to 0.0.0.0:$PORT for Render compatibility
bind = "0.0.0.0:${PORT}"

# Worker configuration - use 2 workers by default, or min(2 * num_cores + 1, 4)
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)

# Use worker threads for better performance
threads = 2

# Timeout configuration (seconds)
timeout = 120
graceful_timeout = 30

# Log configuration
loglevel = "info"
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log errors to stdout

# Worker options
worker_class = "sync"

# Make sure server is accessible from anywhere
forwarded_allow_ips = "*"

# Access control
limit_request_line = 0
limit_request_fields = 100
limit_request_field_size = 8190 