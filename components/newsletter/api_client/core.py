import json
from collections.abc import AsyncIterable
from typing import Protocol, Self, override

import structlog
from dishka import Provider, Scope, provide
from hishel import CacheOptions, SpecificationPolicy
from hishel.httpx import AsyncCacheClient
from httpx import (
    AsyncBaseTransport,
    AsyncClient,
    AsyncHTTPTransport,
    HTTPStatusError,
    Request,
    Response,
    Timeout,
)
from opentelemetry import trace
from pydantic import BaseModel

from .methods import BaseMethod, ParamLocation
from .settings import APIClientSettings


class IAPIClient(Protocol):
    async def __call__[T: BaseModel](self, method: BaseMethod[T]) -> T: ...


class _ErrorResponse(BaseModel):
    error: str
    message: str


class APIException(Exception):
    def __init__(self, error: str, message: str, status_code: int) -> None:
        self.error: str = error
        self.message: str = message
        self.status_code: int = status_code
        super().__init__(f"{error}: {message}")

    @classmethod
    def from_response(cls, response: Response) -> Self:
        try:
            error_response = _ErrorResponse.model_validate_json(response.content)
        except Exception:
            try:
                response.raise_for_status()
            except HTTPStatusError as e:
                error_response = _ErrorResponse(
                    error=e.response.reason_phrase,
                    message=e.response.text,
                )
            else:
                error_response = _ErrorResponse(
                    error="Unknown",
                    message=response.text,
                )

        return cls(
            error=error_response.error,
            message=error_response.message,
            status_code=response.status_code,
        )


class APIClient(IAPIClient):
    def __init__(self, httpx_client: AsyncClient, api_secret_token: str) -> None:
        self.httpx_client: AsyncClient = httpx_client
        self.secret_token: str = api_secret_token
        self.tracer: trace.Tracer = trace.get_tracer("api_client")
        self.logger: structlog.BoundLogger = structlog.get_logger("api_client")

    @override
    async def __call__[T: BaseModel](self, method: BaseMethod[T]) -> T:
        method_name = type(method).__name__
        with self.tracer.start_as_current_span(
            f"api_client.{method_name}",
            attributes={
                "http.method": method.method,
                "http.endpoint": method.endpoint,
                "http.base_url": str(self.httpx_client.base_url),
                "api_client.method": method_name,
            },
        ) as span:
            headers: dict[str, str] | None = None
            logger = self.logger.bind(
                http_method=method.method,
                method_name=method_name,
                endpoint=method.endpoint,
            )
            if method.need_auth:
                headers = {"Authorization": f"SECRET {self.secret_token}"}

            params = method.extract_by_location(ParamLocation.QUERY)
            body = method.extract_by_location(ParamLocation.BODY)

            logger.info(
                "send_request",
                params=json.dumps(params, default=str, ensure_ascii=False)
                if params
                else None,
                body=json.dumps(body, default=str, ensure_ascii=False)
                if body
                else None,
            )

            response = await self.httpx_client.request(
                method=method.method,
                url=method.endpoint,
                params=params if params else None,
                json=body if body else None,
                headers=headers,
            )
            span.set_attribute("http.status_code", response.status_code)

            if response.status_code != method.status_code:
                raise APIException.from_response(response)

            try:
                result = method.load_response(response.content)
            except Exception as e:
                raise APIException(
                    error="Response parsing error",
                    message=str(e),
                    status_code=response.status_code,
                )

            logger.info(
                "response_parsed",
                response=json.dumps(
                    result.model_dump(), default=str, ensure_ascii=False
                ),
            )
            return result


class ForceCacheTransport(AsyncBaseTransport):
    def __init__(self, transport: AsyncBaseTransport, cache_ttl_seconds: int):
        self.transport: AsyncBaseTransport = transport
        self.cache_ttl_seconds: int = cache_ttl_seconds

    @override
    async def handle_async_request(self, request: Request) -> Response:
        response = await self.transport.handle_async_request(request)
        for header in ["cache-control", "expires", "pragma"]:
            response.headers.pop(header, None)
        response.headers["Cache-Control"] = f"public, max-age={self.cache_ttl_seconds}"

        return response


class APIClientProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> APIClientSettings:
        return APIClientSettings()  # type: ignore # pyright: ignore

    @provide(scope=Scope.APP)
    async def httpx_client(
        self, settings: APIClientSettings
    ) -> AsyncIterable[AsyncClient]:
        options = CacheOptions(
            supported_methods=["GET"],
            allow_stale=True,
            shared=False,
        )
        async with AsyncCacheClient(
            base_url=settings.api_base_url,
            follow_redirects=True,
            timeout=Timeout(settings.timeout_seconds),
            policy=SpecificationPolicy(cache_options=options),
            transport=ForceCacheTransport(
                transport=AsyncHTTPTransport(),
                cache_ttl_seconds=settings.cache_ttl_seconds,
            ),
        ) as client:
            yield client

    @provide(scope=Scope.REQUEST)
    def api_client(
        self, httpx_client: AsyncClient, settings: APIClientSettings
    ) -> IAPIClient:
        return APIClient(httpx_client, settings.api_secret_token)
