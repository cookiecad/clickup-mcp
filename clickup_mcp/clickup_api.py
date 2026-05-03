from __future__ import annotations

import json
from typing import Any, Mapping

import httpx


class ClickUpAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class ClickUpClient:
    """HTTP client for ClickUp API v2."""

    def __init__(self, *, api_token: str, base_url: str, debug_http: bool = False) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": api_token,
            "Content-Type": "application/json",
        }
        self._debug_http = debug_http
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(60.0),
            headers=self._headers,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        try:
            if self._debug_http:
                q = f" params={json.dumps(params, default=str)[:1000]}" if params else ""
                b = f" body={json.dumps(json_body, default=str)[:1000]}" if json_body is not None else ""
                print(f"[clickup] {method.upper()} {path}{q}{b}")
            resp = await self._client.request(method.upper(), path, params=params, json=json_body)
        except httpx.RequestError as e:
            raise ClickUpAPIError(f"ClickUp request failed: {e!s}") from e

        content_type = (resp.headers.get("content-type") or "").lower()
        data: Any = None
        if "application/json" in content_type:
            try:
                data = resp.json()
            except Exception:
                data = resp.text
        else:
            data = resp.text

        if resp.status_code >= 400:
            msg = f"ClickUp API error {resp.status_code} for {method.upper()} {path}"
            if isinstance(data, dict) and data.get("err"):
                msg = f"{msg}: {data.get('err')}"
            raise ClickUpAPIError(msg, status_code=resp.status_code, details=data)

        return data


class ClickUpV3Client:
    """HTTP client for ClickUp API v3 (Docs, Pages, etc)."""

    def __init__(self, *, api_token: str, base_url: str, debug_http: bool = False) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": api_token,
            "Content-Type": "application/json",
        }
        self._debug_http = debug_http
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(60.0),
            headers=self._headers,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        try:
            if self._debug_http:
                q = f" params={json.dumps(params, default=str)[:1000]}" if params else ""
                b = f" body={json.dumps(json_body, default=str)[:1000]}" if json_body is not None else ""
                print(f"[clickup-v3] {method.upper()} {path}{q}{b}")
            resp = await self._client.request(method.upper(), path, params=params, json=json_body)
        except httpx.RequestError as e:
            raise ClickUpAPIError(f"ClickUp v3 request failed: {e!s}") from e

        content_type = (resp.headers.get("content-type") or "").lower()
        data: Any = None
        if "application/json" in content_type:
            try:
                data = resp.json()
            except Exception:
                data = resp.text
        else:
            data = resp.text

        if resp.status_code >= 400:
            msg = f"ClickUp v3 API error {resp.status_code} for {method.upper()} {path}"
            if isinstance(data, dict):
                err_msg = data.get("message") or data.get("err")
                if err_msg:
                    msg = f"{msg}: {err_msg}"
            raise ClickUpAPIError(msg, status_code=resp.status_code, details=data)

        return data

