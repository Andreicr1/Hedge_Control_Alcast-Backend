"""
Lightweight KYC/KYP and credit check helpers.
This is a placeholder for real bureau integrations; responses are deterministic based on entity id/name.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

EntityType = Literal["customer", "supplier", "counterparty"]


@dataclass
class CreditResult:
    score: int
    status: str
    bureau: str
    summary: str


def _hash_score(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return 500 + (int(digest[:4], 16) % 350)  # 500-849


def run_credit_check(entity_type: EntityType, entity_id: int, name: str) -> CreditResult:
    bureau = "MockBureau API"
    score = _hash_score(f"{entity_type}:{entity_id}:{name}")
    status = "approved" if score >= 650 else "manual_review"
    summary = (
        "Aprovado automaticamente."
        if status == "approved"
        else "Encaminhar para análise manual de crédito/OFAC."
    )
    return CreditResult(score=score, status=status, bureau=bureau, summary=summary)
