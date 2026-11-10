"""Simple in-memory rate limiter for Flask routes."""

import time
from functools import wraps
from flask import request, jsonify


class RateLimiter:
    def __init__(self):
        self._buckets = {}

    def reset(self):
        """Clear all in-memory buckets. Intended for tests only."""
        self._buckets.clear()

    def limit(self, max_requests, window_seconds):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                key = (request.remote_addr or "unknown", request.endpoint or func.__name__)
                now = time.time()
                bucket = self._buckets.setdefault(key, [])
                # Remove old entries
                bucket[:] = [t for t in bucket if now - t < window_seconds]
                if len(bucket) >= max_requests:
                    return jsonify({"status": "error", "message": "Too many requests. Please try again later."}), 429
                bucket.append(now)
                return func(*args, **kwargs)
            return wrapper
        return decorator


rate_limiter = RateLimiter()