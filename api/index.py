import os
import sys
import traceback
from pathlib import Path

# Add project root to sys.path
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

try:
    from app.main import app as fastapi_app
    import_error = None
except Exception:
    fastapi_app = None
    import_error = traceback.format_exc()


async def app(scope, receive, send):
    """Vercel ASGI entrypoint with fallback error handling and path resolution."""
    if fastapi_app is None:
        import json
        if scope.get("type") == "http":
            body = json.dumps({
                "status": "error",
                "message": "Application failed to import on Vercel",
                "traceback": import_error.splitlines(),
            }).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"access-control-allow-origin", b"*"),
                    (b"access-control-allow-methods", b"*"),
                    (b"access-control-allow-headers", b"*"),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
        return

    # Handle path resolution when Vercel rewrites to /api/index.py
    if scope.get("type") == "http":
        headers_dict = dict(scope.get("headers", []))
        matched = (
            headers_dict.get(b"x-matched-path")
            or headers_dict.get(b"x-vercel-matched-path")
        )
        if matched:
            scope["path"] = matched.decode("utf-8")
        elif scope.get("path") in ("/api/index.py", "/api/index", "/api"):
            # If no matched header was provided, check raw_path or default to /
            raw = scope.get("raw_path")
            if raw and raw not in (b"/api/index.py", b"/api/index"):
                scope["path"] = raw.decode("utf-8")

    await fastapi_app(scope, receive, send)
