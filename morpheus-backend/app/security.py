import logging
import hashlib
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException, status
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Small fixed-window limiter for expensive AI endpoints.

    Railway runs this app as a small single service today, so an in-process
    limiter is enough to stop accidental bursts and simple cost-burn attempts.
    Move this to Redis if the API is scaled to multiple replicas.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        hits = self._hits[key]

        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please wait a few minutes and try again.",
            )

        hits.append(now)


processing_rate_limiter = InMemoryRateLimiter(
    max_requests=settings.PROCESS_RATE_LIMIT_REQUESTS,
    window_seconds=settings.PROCESS_RATE_LIMIT_WINDOW_SECONDS,
)


def enforce_processing_rate_limit(user_id: str) -> None:
    processing_rate_limiter.check(f"dream-processing:{user_id}")


class RequestTooLargeError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RequestSizeLimitMiddleware:
    """Reject oversized processing requests before they reach route handlers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit, message = self._limit_for_path(str(scope.get("path", "")).rstrip("/"))
        if limit is None:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        try:
            self._enforce_pre_auth_rate_limit(scope, headers)
        except HTTPException as exc:
            await self._reject(
                scope,
                send,
                str(exc.detail),
                status_code=exc.status_code,
            )
            return

        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length.decode("ascii")) > limit:
                    await self._reject(scope, send, message)
                    return
            except ValueError:
                await self._reject(scope, send, "Invalid request headers.")
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            event = await receive()
            if event["type"] == "http.request":
                received += len(event.get("body", b""))
                if received > limit:
                    raise RequestTooLargeError(message)
            return event

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLargeError as exc:
            await self._reject(scope, send, exc.message)

    @staticmethod
    def _limit_for_path(path: str) -> tuple[Optional[int], str]:
        if path.endswith("/dreams/process-text"):
            return settings.MAX_TEXT_REQUEST_BYTES, "Request body is too large."
        if path.endswith("/dreams/process"):
            return settings.MAX_AUDIO_UPLOAD_BYTES + 1024 * 1024, "Uploaded file is too large."
        return None, ""

    @staticmethod
    def _enforce_pre_auth_rate_limit(scope: Scope, headers: dict[bytes, bytes]) -> None:
        auth_header = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
        if auth_header:
            digest = hashlib.sha256(auth_header.encode("utf-8")).hexdigest()
            key = f"processing-auth:{digest}"
        else:
            client = scope.get("client")
            client_host = client[0] if client else "unknown"
            key = f"processing-ip:{client_host}"

        processing_rate_limiter.check(key)

    @staticmethod
    async def _reject(
        scope: Scope,
        send: Send,
        message: str,
        status_code: int = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    ) -> None:
        async def empty_receive() -> Message:
            return {"type": "http.disconnect"}

        response = JSONResponse(
            status_code=status_code,
            content={"detail": message},
        )
        await response(scope, empty_receive, send)


def client_safe_error(message: str = "The request could not be completed.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=message,
    )
