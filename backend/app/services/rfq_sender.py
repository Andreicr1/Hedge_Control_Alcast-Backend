"""
RFQ sender connectors (email/API/WhatsApp) with idempotent provider ids and basic retry hooks.
Replace channel-specific functions with real integrations and error handling.
"""

import uuid
from typing import Any, Dict, Optional

from app.models.domain import SendStatus


class SendResult:
    def __init__(
        self,
        status: SendStatus,
        provider_message_id: Optional[str] = None,
        error: Optional[str] = None,
    ):
        self.status = status
        self.provider_message_id = provider_message_id
        self.error = error


def _build_provider_id(channel: str, idempotency_key: Optional[str]) -> str:
    """
    Deterministic provider id when an idempotency key is supplied so repeated calls
    reuse the same remote identifier. Falls back to uuid4 when not provided.
    """
    if idempotency_key:
        return f"{channel}-{uuid.uuid5(uuid.NAMESPACE_URL, f'rfq:{channel}:{idempotency_key}')}"
    return f"{channel}-{uuid.uuid4()}"


def send_rfq_message(
    channel: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    idempotency_key: Optional[str] = None,
    max_retries: int = 1,
) -> SendResult:
    """
    Dispatcher by channel with idempotent provider ids and basic retry.

    metadata supports testing hooks:
    - force_failure: bool to return failed status.
    - async_mode: bool to mark status as queued (simulating async providers).
    """
    meta = metadata or {}
    provider_id = _build_provider_id(channel, idempotency_key)
    retries = max(1, max_retries)

    last_result: Optional[SendResult] = None
    failure_budget = 0
    try:
        failure_budget = int(meta.get("failures_before_success", 0))
    except (TypeError, ValueError):
        failure_budget = 0

    for attempt_index in range(retries):
        force_failure = meta.get("force_failure") or (attempt_index < failure_budget)
        meta_with_flags = {**meta, "_force_failure_override": force_failure}
        if channel == "email":
            result = _send_email(message, meta_with_flags, provider_id)
        elif channel == "api":
            result = _send_api(message, meta_with_flags, provider_id)
        elif channel == "whatsapp":
            result = _send_whatsapp(message, meta_with_flags, provider_id)
        else:
            result = SendResult(status=SendStatus.sent, provider_message_id=provider_id)

        last_result = result
        if result.status != SendStatus.failed:
            return result

    return last_result or SendResult(
        status=SendStatus.failed, provider_message_id=provider_id, error="unknown error"
    )


def _send_email(message: str, meta: Dict[str, Any], provider_id: str) -> SendResult:
    # meta may contain: to, subject, cc, bcc, force_failure, async_mode
    if meta.get("force_failure") or meta.get("_force_failure_override"):
        return SendResult(
            status=SendStatus.failed, provider_message_id=provider_id, error="email send failed"
        )
    status = SendStatus.queued if meta.get("async_mode") else SendStatus.sent
    return SendResult(status=status, provider_message_id=provider_id)


def _send_api(message: str, meta: Dict[str, Any], provider_id: str) -> SendResult:
    # meta may contain: endpoint, headers, payload overrides, force_failure, async_mode
    if meta.get("force_failure") or meta.get("_force_failure_override"):
        return SendResult(
            status=SendStatus.failed, provider_message_id=provider_id, error="api send failed"
        )
    status = SendStatus.queued if meta.get("async_mode") else SendStatus.sent
    return SendResult(status=status, provider_message_id=provider_id)


def _send_whatsapp(message: str, meta: Dict[str, Any], provider_id: str) -> SendResult:
    # meta may contain: phone, template_id, locale, force_failure, async_mode
    if meta.get("force_failure") or meta.get("_force_failure_override"):
        return SendResult(
            status=SendStatus.failed, provider_message_id=provider_id, error="whatsapp send failed"
        )
    status = SendStatus.queued if meta.get("async_mode") else SendStatus.sent
    return SendResult(status=status, provider_message_id=provider_id)
