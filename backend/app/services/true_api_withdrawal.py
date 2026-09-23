"""WMS-517 True API transport; no workflow, automatic retries or UI wiring.

Contract: https://docs.crpt.ru/gismt/True_API/ (v731.0, 2026-09-23).
The caller must durably record a create attempt BEFORE calling create_document and
persist its result before another external call. Cancellation/crash during create
is an uncertain outcome, even if this coroutine never returns an exception.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx

MAX_CISES = 1000
MAX_DOCUMENT_CISES = 30_000
MAX_DOCUMENT_BYTES = 30_000_000
MAX_REQUESTS_PER_SECOND = 50


class Environment(StrEnum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


@dataclass(frozen=True)
class TrueApiConfig:
    environment: Environment
    timeout_seconds: float = 30.0
    # B3: explicitly enabled by trusted server configuration only after the
    # browser auth profile has evidence. No profile parameters are guessed here.
    browser_auth_profile_verified: bool = False

    def __post_init__(self) -> None:
        if self.environment not in {Environment.SANDBOX, Environment.PRODUCTION}:
            raise ValueError("Unknown True API environment")
        if self.timeout_seconds <= 0:
            raise ValueError("True API timeout must be positive")

    def base_url(self, version: int) -> str:
        if version not in {3, 4}:
            raise ValueError("Unsupported True API version")
        host = (
            "markirovka.sandbox.crptech.ru"
            if self.environment == Environment.SANDBOX
            else "markirovka.crpt.ru"
        )
        return f"https://{host}/api/v{version}/true-api"

    def require_verified_auth_profile(self) -> None:
        if self.browser_auth_profile_verified is not True:
            raise ValueError("B3: browser authentication signature profile is not verified")


class SharedParticipantLimiter(Protocol):
    async def acquire(self, environment: Environment, participant_inn: str) -> None:
        """Reserve capacity atomically across all workers; failure must fail closed."""
        ...


class RedisScriptExecutor(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> Any: ...


# Atomic server-time pacing. No future reservations: a delayed worker must obtain
# a fresh grant, so accumulated waiters cannot wake up into an unchecked burst.
# 20,001us spacing admits at most 50 grants in any one-second interval.
_ACQUIRE_SCRIPT = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000000 + tonumber(t[2])
local last = tonumber(redis.call('GET', KEYS[1]) or '0')
local wait = last + 20001 - now
if wait > 0 then return wait end
redis.call('SET', KEYS[1], string.format('%.0f', now), 'PX', 2000)
return 0
"""


class RedisParticipantLimiter:
    """Uses the existing Redis service; never falls back to local pacing.

    All clients for a participant/environment must use the same Redis and key
    namespace. Redis durability/availability and wiring belong to the worker.
    """

    def __init__(self, redis: RedisScriptExecutor) -> None:
        self._redis = redis

    async def acquire(self, environment: Environment, participant_inn: str) -> None:
        _validate_inn(participant_inn)
        key = f"wms:true-api:rate:{environment}:{participant_inn}"
        while True:
            wait_us = int(await self._redis.eval(_ACQUIRE_SCRIPT, 1, key))
            if wait_us == 0:
                return
            if wait_us < 0:
                raise RuntimeError("Invalid True API limiter response")
            await asyncio.sleep(wait_us / 1_000_000)


class CreateOutcome(StrEnum):
    DEFINITE_REJECT = "definite_reject"
    UNCERTAIN = "uncertain"


class TrueApiError(Exception):
    """Safe exception text; raw response is restricted audit data, never log it."""

    def __init__(
        self,
        reason: str,
        *,
        status_code: int | None = None,
        response_body: bytes = b"",
        create_outcome: CreateOutcome | None = None,
    ) -> None:
        self.reason = reason
        self.status_code = status_code
        self.response_body = response_body
        self.create_outcome = create_outcome
        super().__init__(f"True API {reason}; HTTP {status_code}")


@dataclass(frozen=True)
class AuthChallenge:
    uuid: str
    data: str = field(repr=False)


@dataclass(frozen=True)
class AuthSession:
    environment: Environment
    participant_inn: str
    expires_at: datetime
    token: str = field(repr=False)


@dataclass(frozen=True)
class CisInfo:
    requested_cis: str = field(repr=False)
    cis: str | None = field(repr=False)
    product_group: str | None
    product_group_id: int | None
    owner_inn: str | None
    status: str | None
    status_ex: str | None
    gtin: str | None
    error_code: Any = field(repr=False)
    error_message: Any = field(repr=False)
    raw: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class CisesResponse:
    # Only unambiguous requested identities appear here. Missing/duplicate rows
    # must fail preflight; raw preserves provider errors without inventing one.
    by_cis: dict[str, CisInfo] = field(repr=False)
    unresolved: tuple[str, ...] = field(repr=False)
    raw: Any = field(repr=False)
    status_code: int


class DocumentOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PENDING = "pending"
    UNKNOWN = "unknown"


def document_outcome(status: str | None) -> DocumentOutcome:
    if status == "CHECKED_OK":
        return DocumentOutcome.SUCCEEDED
    if status in {"CHECKED_NOT_OK", "PARSE_ERROR", "PROCESSING_ERROR"}:
        return DocumentOutcome.FAILED
    if status in {"IN_PROGRESS", "WAIT_FOR_CONTINUATION"}:
        return DocumentOutcome.PENDING
    return DocumentOutcome.UNKNOWN


@dataclass(frozen=True)
class DocumentInfo:
    document_id: str
    status: str | None
    body: Any = field(repr=False)
    errors: Any = field(repr=False)
    common_errors: Any = field(repr=False)
    raw: dict[str, Any] = field(repr=False)

    @property
    def outcome(self) -> DocumentOutcome:
        # A shipment response must never be interpreted as a withdrawal success.
        if self.raw.get("type") != "LK_RECEIPT":
            return DocumentOutcome.UNKNOWN
        return document_outcome(self.status)


@dataclass(frozen=True)
class DocumentCursor:
    document_id: str
    doc_date: str


@dataclass(frozen=True)
class DocumentPage:
    results: tuple[dict[str, Any], ...] = field(repr=False)
    next_page: bool
    next_cursor: DocumentCursor | None


def _validate_inn(value: str) -> None:
    if re.fullmatch(r"(?:[0-9]{10}|[0-9]{12})", value) is None:
        raise ValueError("Participant INN must contain 10 or 12 digits")


def _uuid(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected UUID string")
    return str(UUID(value))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _aware(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _signature(value: str) -> str:
    # Browser must already have removed newlines; never silently rewrite it here.
    try:
        if not base64.b64decode(value, validate=True):
            raise ValueError("Empty signature")
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Signature must be nonempty base64 without whitespace") from exc
    return value


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _moscow_today() -> date:
    return datetime.now(UTC).astimezone(ZoneInfo("Europe/Moscow")).date()


def _validate_action_date(value: Any) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError("action_date must be a calendar date in YYYY-MM-DD format")
    try:
        action_date = date.fromisoformat(value)
    except ValueError:
        raise ValueError("action_date must be a valid calendar date") from None
    today = _moscow_today()
    try:
        oldest_date = today.replace(year=today.year - 5)
    except ValueError:
        # February 29 has no matching day five years earlier.
        oldest_date = today.replace(year=today.year - 5, day=28)
    if not oldest_date <= action_date <= today:
        raise ValueError("action_date must be within the last five years in Europe/Moscow")


def parse_cises(data: Any, requested: list[str], status_code: int = 200) -> CisesResponse:
    rows = data if isinstance(data, list) else [data]
    by_cis: dict[str, CisInfo] = {}
    duplicates: set[str] = set()
    requested_set = set(requested)
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("cisInfo"), dict):
            continue
        info = row["cisInfo"]
        key = info.get("requestedCis")
        if not isinstance(key, str) or key not in requested_set:
            continue
        if key in by_cis:
            duplicates.add(key)
        group_id = info.get("productGroupId")
        by_cis[key] = CisInfo(
            requested_cis=key,
            cis=_string(info.get("cis")),
            product_group=_string(info.get("productGroup")),
            product_group_id=group_id if type(group_id) is int else None,
            owner_inn=_string(info.get("ownerInn")),
            status=_string(info.get("status")),
            status_ex=_string(info.get("statusEx")),
            gtin=_string(info.get("gtin")),
            error_code=row.get("errorCode"),
            error_message=row.get("errorMessage"),
            raw=row,
        )
    for key in duplicates:
        by_cis.pop(key)
    return CisesResponse(
        by_cis, tuple(code for code in requested if code not in by_cis), data, status_code
    )


class TrueApiWithdrawalClient:
    """Explicit injected HTTP transport and shared limiter, with no retry loop.

    Use a dedicated httpx client without retrying transports/event hooks. This
    class disables redirects on every request, including when the client enables
    them globally. Tokens are server-only and never included in repr/errors.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        config: TrueApiConfig,
        limiter: SharedParticipantLimiter,
        participant_inn: str,
    ) -> None:
        _validate_inn(participant_inn)
        self._http = http_client
        self.config = config
        self._limiter = limiter
        self.participant_inn = participant_inn

    async def _request(
        self,
        method: str,
        version: int,
        path: str,
        *,
        auth: AuthSession | None = None,
        params: dict[str, str] | None = None,
        payload: Any = None,
        create: bool = False,
        allowed_statuses: frozenset[int] = frozenset({200}),
    ) -> httpx.Response:
        headers = {"Accept": "application/json"}
        if auth is not None:
            if (
                auth.environment != self.config.environment
                or auth.participant_inn != self.participant_inn
                or _aware(auth.expires_at) <= datetime.now(UTC)
            ):
                raise ValueError("Expired or mismatched True API auth session")
            headers["Authorization"] = f"Bearer {_uuid(auth.token)}"
        await self._limiter.acquire(self.config.environment, self.participant_inn)
        # Limiter waits may outlive a token; check again before starting the call.
        if auth is not None and _aware(auth.expires_at) <= datetime.now(UTC):
            raise ValueError("Expired True API auth session")
        try:
            response = await self._http.request(
                method,
                self.config.base_url(version) + path,
                headers=headers,
                params=params,
                json=payload,
                timeout=self.config.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.RequestError:
            # Never attach the original exception/request (Authorization/body).
            raise TrueApiError(
                "transport_failure",
                create_outcome=CreateOutcome.UNCERTAIN if create else None,
            ) from None
        if response.status_code not in allowed_statuses:
            outcome = None
            if create:
                outcome = (
                    CreateOutcome.DEFINITE_REJECT
                    if response.status_code in {400, 401, 403, 422}
                    else CreateOutcome.UNCERTAIN
                )
            raise TrueApiError(
                "http_failure",
                status_code=response.status_code,
                response_body=response.content,
                create_outcome=outcome,
            )
        return response

    @staticmethod
    def _json(response: httpx.Response, *, create: bool = False) -> Any:
        try:
            return response.json()
        except ValueError:
            raise TrueApiError(
                "invalid_json",
                status_code=response.status_code,
                response_body=response.content,
                create_outcome=CreateOutcome.UNCERTAIN if create else None,
            ) from None

    @staticmethod
    def _invalid(response: httpx.Response, *, auth: bool = False) -> TrueApiError:
        return TrueApiError(
            "invalid_contract",
            status_code=response.status_code,
            # Successful auth responses contain secrets; don't put them in audit errors.
            response_body=b"" if auth else response.content,
        )

    async def challenge(self) -> AuthChallenge:
        response = await self._request("GET", 3, "/auth/key")
        try:
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("data"), str):
                raise ValueError
            if not data["data"]:
                raise ValueError
            return AuthChallenge(_uuid(data.get("uuid")), data["data"])
        except (ValueError, TypeError):
            raise self._invalid(response, auth=True) from None

    async def sign_in(
        self,
        challenge_uuid: str,
        attached_signature: str,
        *,
        certificate_expires_at: datetime,
        mchd_inn: str | None = None,
        mchd_expires_at: datetime | None = None,
    ) -> AuthSession:
        self.config.require_verified_auth_profile()
        started_at = datetime.now(UTC)
        expiry_bounds = [started_at + timedelta(hours=10), _aware(certificate_expires_at)]
        payload: dict[str, Any] = {
            "uuid": _uuid(challenge_uuid),
            "data": _signature(attached_signature),
            "unitedToken": True,
        }
        if mchd_inn is not None:
            if mchd_inn != self.participant_inn or mchd_expires_at is None:
                raise ValueError("MChD must belong to participant and have a known expiry")
            payload["inn"] = mchd_inn
            expiry_bounds.append(_aware(mchd_expires_at))
        elif mchd_expires_at is not None:
            raise ValueError("MChD expiry requires participant INN")
        if min(expiry_bounds) <= started_at:
            raise ValueError("Certificate or MChD expired")
        response = await self._request("POST", 3, "/auth/simpleSignIn", payload=payload)
        try:
            data = response.json()
            token = _uuid(data["uuidToken"])
            expiry_bounds.append(_aware(datetime.fromisoformat(data["expireDate"])))
            expires_at = min(expiry_bounds)
            if expires_at <= datetime.now(UTC):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise self._invalid(response, auth=True) from None
        return AuthSession(self.config.environment, self.participant_inn, expires_at, token)

    async def cises_info(self, auth: AuthSession, codes: list[str]) -> CisesResponse:
        if not 1 <= len(codes) <= MAX_CISES or len(set(codes)) != len(codes):
            raise ValueError("cises/info requires 1..1000 unique identification codes")
        if any(not 18 <= len(code) <= 74 for code in codes):
            raise ValueError("cises/info identification codes must contain 18..74 characters")
        response = await self._request(
            "POST",
            3,
            "/cises/info",
            auth=auth,
            payload=codes,
            allowed_statuses=frozenset({200, 404}),
        )
        return parse_cises(self._json(response), codes, response.status_code)

    async def create_document(
        self, auth: AuthSession, *, pg: str, exact_payload: bytes, detached_signature: str
    ) -> str:
        self.config.require_verified_auth_profile()
        if not pg:
            raise ValueError("Product group is required")
        if not exact_payload or len(exact_payload) > MAX_DOCUMENT_BYTES:
            raise ValueError("Document must contain at most 30 MB")
        # Read only for boundary validation; send the ORIGINAL bytes unchanged.
        data = json.loads(exact_payload.decode("utf-8"))
        if not isinstance(data, dict) or data.get("inn") != self.participant_inn:
            raise ValueError("Document participant mismatch")
        _validate_action_date(data.get("action_date"))
        products = data.get("products")
        if data.get("action") != "DISTANCE" or not isinstance(products, list):
            raise ValueError("Expected DISTANCE withdrawal products")
        if not 1 <= len(products) <= MAX_DOCUMENT_CISES:
            raise ValueError("Document must contain 1..30000 codes")
        codes: list[str] = []
        for product in products:
            if not isinstance(product, dict):
                raise ValueError("Each document product must be an object")
            code = product.get("cis")
            if not isinstance(code, str) or not code:
                raise ValueError("Document CIS is required")
            cost = product.get("product_cost")
            if type(cost) is not int or not 0 <= cost <= 99_999_999_999_999_999:
                raise ValueError("product_cost must be integer kopecks in 0..99999999999999999")
            codes.append(code)
        if len(set(codes)) != len(codes):
            raise ValueError("Duplicate document CIS")
        payload = {
            "document_format": "MANUAL",
            "product_document": base64.b64encode(exact_payload).decode("ascii"),
            "type": "LK_RECEIPT",
            "signature": _signature(detached_signature),
        }
        response = await self._request(
            "POST",
            3,
            "/lk/documents/create",
            auth=auth,
            params={"pg": pg},
            payload=payload,
            create=True,
            allowed_statuses=frozenset({200, 201}),
        )
        # The documented response is the ID itself, not an invented {id: ...} object.
        try:
            value = response.json()
        except ValueError:
            value = response.text.strip()
        try:
            return _uuid(value)
        except ValueError:
            raise TrueApiError(
                "missing_document_id",
                status_code=response.status_code,
                response_body=response.content,
                create_outcome=CreateOutcome.UNCERTAIN,
            ) from None

    async def list_documents(
        self,
        auth: AuthSession,
        *,
        pg: str,
        date_from: datetime,
        date_to: datetime,
        cursor: DocumentCursor | None = None,
        limit: int = 1000,
    ) -> DocumentPage:
        if not pg or not 1 <= limit <= 1000 or _aware(date_from) > _aware(date_to):
            raise ValueError("Invalid document search window/group/limit")
        params = {
            "pg": pg,
            "dateFrom": _timestamp(date_from),
            "dateTo": _timestamp(date_to),
            "senderInn": self.participant_inn,
            "documentType": "LK_RECEIPT",
            "documentFormat": "MANUAL",
            "limit": str(limit),
            "order": "ASC",
        }
        if cursor is not None:
            params.update(
                did=cursor.document_id, orderedColumnValue=cursor.doc_date, pageDir="NEXT"
            )
        response = await self._request("GET", 4, "/doc/list", auth=auth, params=params)
        data = self._json(response)
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("results"), list)
            or type(data.get("nextPage")) is not bool
            or any(not isinstance(row, dict) for row in data["results"])
        ):
            raise self._invalid(response)
        results = data["results"]
        next_cursor = None
        if data["nextPage"]:
            if not results:
                raise self._invalid(response)
            last = results[-1]
            if not _string(last.get("number")) or not _string(last.get("docDate")):
                raise self._invalid(response)
            next_cursor = DocumentCursor(last["number"], last["docDate"])
            if next_cursor == cursor:
                raise self._invalid(response)
        return DocumentPage(tuple(results), data["nextPage"], next_cursor)

    async def document_info(self, auth: AuthSession, *, pg: str, document_id: str) -> DocumentInfo:
        if not pg:
            raise ValueError("Product group is required")
        document_id = _uuid(document_id)
        response = await self._request(
            "GET",
            4,
            f"/doc/{quote(document_id, safe='')}/info",
            auth=auth,
            params={"pg": pg, "body": "true"},
        )
        data = self._json(response)
        # v4 info returns an array, even when one document was requested.
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise self._invalid(response)
        row = data[0]
        if row.get("number") != document_id or row.get("productGroup") != [pg]:
            raise self._invalid(response)
        return DocumentInfo(
            document_id,
            _string(row.get("status")),
            row.get("body"),
            row.get("errors"),
            row.get("commonErrors"),
            row,
        )
