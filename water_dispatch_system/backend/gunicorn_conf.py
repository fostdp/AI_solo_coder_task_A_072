import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
keepalive = 120
timeout = 120
graceful_timeout = 30
max_requests = 5000
max_requests_jitter = 500
accesslog = "-"
errorlog = "-"
loglevel = "info"
preload_app = True
