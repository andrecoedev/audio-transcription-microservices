"""Small Redis-backed, atomic fixed-window limits for expensive API writes."""

import hashlib
import hmac
import logging
import time

from fastapi import HTTPException, Request

from ..config import settings
from ..workers.config import get_redis_connection


logger = logging.getLogger(__name__)

_CHECK_AND_INCREMENT = """
for index, key in ipairs(KEYS) do
    if tonumber(redis.call('GET', key) or '0') >= tonumber(ARGV[index * 2 - 1]) then
        return index
    end
end
for index, key in ipairs(KEYS) do
    local count = redis.call('INCR', key)
    if count == 1 then
        redis.call('EXPIRE', key, tonumber(ARGV[index * 2]))
    end
end
return 0
"""


def enforce_rate_limit(request: Request, category: str, identity: str | None = None) -> None:
    """Reject before expensive work. Never trust client-supplied forwarded IPs."""
    ip = request.client.host if request.client else "unknown"
    if category == "login":
        rules = [
            ("login-ip", ip, settings.LOGIN_RATE_LIMIT_PER_IP, 300),
            ("login-account", (identity or "").casefold(), settings.LOGIN_RATE_LIMIT_PER_ACCOUNT, 300),
        ]
    elif category == "upload-ip":
        rules = [("upload-ip", ip, settings.UPLOAD_RATE_LIMIT_PER_IP, 3600)]
    elif category == "job-user":
        rules = [("job-user", identity or "", settings.JOB_RATE_LIMIT_PER_USER, 3600)]
    elif category == "provider-settings-user":
        # Same configurable ceiling, independent counter from job creation.
        rules = [("provider-settings-user", identity or "", settings.JOB_RATE_LIMIT_PER_USER, 3600)]
    elif category == "signup":
        rules = [("signup-ip", ip, settings.SIGNUP_RATE_LIMIT_PER_IP, 3600)]
    elif category == "guest-session":
        rules = [("guest-session-ip", ip, settings.GUEST_SESSION_RATE_LIMIT_PER_IP, 3600)]
    elif category == "public-job":
        rules = [
            ("public-job-ip", ip, settings.PUBLIC_JOB_RATE_LIMIT_PER_IP, 3600),
            ("public-job-global", "all", settings.PUBLIC_JOB_RATE_LIMIT_GLOBAL, 3600),
        ]
    else:
        raise ValueError("Unsupported rate limit category")

    now = int(time.time())
    secret = (settings.SECRET_KEY or "local-rate-limit-key").encode()
    keys = []
    args = []
    for name, subject, limit, window in rules:
        digest = hmac.new(secret, subject.encode(), hashlib.sha256).hexdigest()
        keys.append(f"rate-limit:{name}:{digest}:{now // window}")
        args.extend((limit, window + 1))
    try:
        exceeded = int(get_redis_connection().eval(_CHECK_AND_INCREMENT, len(keys), *keys, *args))
    except Exception:
        logger.warning("Redis rate limiting unavailable for %s", category)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from None
    if exceeded:
        window = rules[exceeded - 1][3]
        raise HTTPException(
            status_code=429,
            detail="Too many requests; please retry later",
            headers={"Retry-After": str(window - now % window)},
        )
