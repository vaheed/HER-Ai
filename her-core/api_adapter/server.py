from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Awaitable, Callable
from uuid import uuid4

from aiohttp import web

logger = logging.getLogger(__name__)


def _openapi_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "HER API Adapter",
            "version": "1.1.0",
            "description": (
                "HTTP/OpenAPI adapter for chatting with HER without Telegram. "
                "Includes OpenAI-compatible endpoints for OpenWebUI and similar clients."
            ),
        },
        "servers": [{"url": "/", "description": "Runtime server"}],
        "paths": {
            "/api/health": {
                "get": {
                    "summary": "API adapter health",
                    "responses": {"200": {"description": "Healthy"}},
                }
            },
            "/api/v1/chat": {
                "post": {
                    "summary": "Native HER chat endpoint",
                    "responses": {"200": {"description": "Chat response"}},
                }
            },
            "/v1/models": {
                "get": {
                    "summary": "OpenAI-compatible model listing",
                    "responses": {"200": {"description": "Model list"}},
                }
            },
            "/v1/chat/completions": {
                "post": {
                    "summary": "OpenAI-compatible chat completions",
                    "responses": {"200": {"description": "Chat completion"}},
                }
            },
            "/api/openapi.json": {
                "get": {
                    "summary": "OpenAPI spec",
                    "responses": {"200": {"description": "Spec"}},
                }
            },
        },
    }


class OpenAPIAdapterServer:
    """Expose HER runtime through HTTP with OpenAPI/OpenAI-compatible surfaces."""

    def __init__(
        self,
        handler: Callable[[int, str, int | None, bool], Awaitable[dict[str, Any]]],
        host: str = "0.0.0.0",
        port: int = 8082,
        bearer_token: str | None = None,
        model_name: str = "her-chat-1",
    ) -> None:
        self._handler = handler
        self._host = host
        self._port = int(port)
        self._bearer_token = (bearer_token or "").strip()
        self._model_name = (model_name or "her-chat-1").strip()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        app = web.Application(middlewares=[self._cors_middleware])
        app.router.add_get("/api/health", self._health)
        app.router.add_get("/api/openapi.json", self._openapi)
        app.router.add_get("/api/docs", self._docs)

        app.router.add_post("/api/v1/chat", self._chat)
        app.router.add_get("/v1/models", self._openai_models)
        app.router.add_post("/v1/chat/completions", self._openai_chat_completions)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        logger.info("OpenAPI adapter started at http://%s:%s/api/docs", self._host, self._port)

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()

    @web.middleware
    async def _cors_middleware(self, request: web.Request, handler: Callable[[web.Request], Any]) -> web.StreamResponse:
        if request.method == "OPTIONS":
            resp = web.Response(status=204)
        else:
            resp = await handler(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        return resp

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _openapi(self, request: web.Request) -> web.Response:
        return web.json_response(_openapi_spec())

    async def _docs(self, request: web.Request) -> web.Response:
        html = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\"/>
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/>
  <title>HER API Docs</title>
  <link rel=\"stylesheet\" href=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui.css\" />
</head>
<body>
  <div id=\"swagger-ui\"></div>
  <script src=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js\"></script>
  <script>
    SwaggerUIBundle({ url: '/api/openapi.json', dom_id: '#swagger-ui' });
  </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def _chat(self, request: web.Request) -> web.Response:
        auth_error = self._check_auth(request)
        if auth_error is not None:
            return auth_error

        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        user_id_raw = payload.get("user_id")
        message = str(payload.get("message", "")).strip()
        debug = bool(payload.get("debug", False))

        if user_id_raw is None:
            return web.json_response({"error": "'user_id' is required"}, status=400)
        if not message:
            return web.json_response({"error": "'message' is required"}, status=400)

        user_id = self._coerce_user_id(user_id_raw)
        if user_id is None:
            return web.json_response({"error": "'user_id' is invalid"}, status=400)

        chat_id_raw = payload.get("chat_id")
        chat_id: int | None = None
        if chat_id_raw is not None:
            chat_id = self._coerce_user_id(chat_id_raw)
            if chat_id is None:
                return web.json_response({"error": "'chat_id' must be numeric"}, status=400)

        try:
            result = await self._handler(user_id, message, chat_id, debug)
            return web.json_response(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("API adapter chat request failed: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)

    async def _openai_models(self, request: web.Request) -> web.Response:
        auth_error = self._check_auth(request)
        if auth_error is not None:
            return auth_error

        created = int(time.time())
        payload = {
            "object": "list",
            "data": [
                {
                    "id": self._model_name,
                    "object": "model",
                    "created": created,
                    "owned_by": "her-ai",
                }
            ],
        }
        return web.json_response(payload)

    async def _openai_chat_completions(self, request: web.Request) -> web.StreamResponse:
        auth_error = self._check_auth(request)
        if auth_error is not None:
            return auth_error

        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": {"message": "Invalid JSON", "type": "invalid_request_error"}}, status=400)

        message_text = self._extract_latest_user_message(payload.get("messages"))
        if not message_text:
            return web.json_response(
                {"error": {"message": "messages with at least one user entry are required", "type": "invalid_request_error"}},
                status=400,
            )

        user_id = self._coerce_user_id(payload.get("user"))
        if user_id is None:
            user_id = self._coerce_user_id(request.headers.get("X-User-Id"))
        if user_id is None:
            user_id = self._fallback_user_id_from_request(request)

        stream = bool(payload.get("stream", False))
        model = str(payload.get("model") or self._model_name)

        try:
            result = await self._handler(user_id, message_text, None, False)
        except Exception as exc:  # noqa: BLE001
            logger.exception("OpenAI chat completion request failed: %s", exc)
            return web.json_response({"error": {"message": str(exc), "type": "server_error"}}, status=500)

        response_text = str(result.get("response", "")).strip() or "I am here with you."
        chat_id = f"chatcmpl-{uuid4().hex}"
        created = int(time.time())

        if stream:
            return await self._stream_openai_completion(request, chat_id, created, model, response_text)

        prompt_tokens = max(1, len(message_text.split()))
        completion_tokens = max(1, len(response_text.split()))
        body = {
            "id": chat_id,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": response_text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
        return web.json_response(body)

    async def _stream_openai_completion(
        self,
        request: web.Request,
        chat_id: str,
        created: int,
        model: str,
        response_text: str,
    ) -> web.StreamResponse:
        resp = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await resp.prepare(request)

        first = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
        await resp.write(f"data: {json.dumps(first, ensure_ascii=False)}\n\n".encode("utf-8"))

        for token in self._token_chunks(response_text):
            chunk = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
            }
            await resp.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8"))

        end_chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        await resp.write(f"data: {json.dumps(end_chunk, ensure_ascii=False)}\n\n".encode("utf-8"))
        await resp.write(b"data: [DONE]\n\n")
        await resp.write_eof()
        return resp

    def _check_auth(self, request: web.Request) -> web.Response | None:
        if not self._bearer_token:
            return None

        auth_header = str(request.headers.get("Authorization", ""))
        if not auth_header.startswith("Bearer "):
            return web.json_response(
                {"error": {"message": "Missing bearer token", "type": "authentication_error"}},
                status=401,
            )

        provided = auth_header.removeprefix("Bearer ").strip()
        if provided != self._bearer_token:
            return web.json_response(
                {"error": {"message": "Invalid bearer token", "type": "authentication_error"}},
                status=401,
            )
        return None

    @staticmethod
    def _coerce_user_id(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return None
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            try:
                return int(text)
            except ValueError:
                return None

        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return int(digest[:10], 16)

    @staticmethod
    def _fallback_user_id_from_request(request: web.Request) -> int:
        identity = (
            request.headers.get("X-Forwarded-For")
            or request.headers.get("X-Real-IP")
            or (request.remote or "anonymous")
        )
        digest = hashlib.sha256(str(identity).encode("utf-8")).hexdigest()
        return int(digest[:10], 16)

    def _extract_latest_user_message(self, messages: Any) -> str:
        if not isinstance(messages, list) or not messages:
            return ""

        latest_user = ""
        for item in messages:
            if not isinstance(item, dict):
                continue
            if str(item.get("role", "")).strip().lower() != "user":
                continue
            latest_user = self._message_content_to_text(item.get("content"))

        return latest_user.strip()

    @staticmethod
    def _message_content_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for part in content:
                if isinstance(part, str):
                    chunks.append(part)
                    continue
                if not isinstance(part, dict):
                    continue
                text = part.get("text") if part.get("type") in {"text", None} else ""
                if text:
                    chunks.append(str(text))
            return "\n".join(chunks)
        return str(content or "")

    @staticmethod
    def _token_chunks(text: str) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        return [word + (" " if idx < len(words) - 1 else "") for idx, word in enumerate(words)]
