"""MySQL-backed store for saved company column mappings."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update

from app.database.connection import get_db_session
from app.database.models import CompanyMapping


class MappingStore:
    async def save(
        self,
        company_id: str,
        company_name: str,
        mapping_config: Dict[str, Any],
        source_columns: List[str],
        confidence_score: float,
        user_id: Optional[str] = None,
    ) -> str:
        async with get_db_session() as db:
            # Upsert by company_id
            result = await db.execute(
                select(CompanyMapping).where(CompanyMapping.company_id == company_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.mapping_config   = mapping_config
                existing.source_columns   = source_columns
                existing.confidence_score = confidence_score
                existing.company_name     = company_name
                existing.last_used_at     = datetime.now(timezone.utc)
                db.add(existing)
                return existing.id
            else:
                new = CompanyMapping(
                    id=str(uuid.uuid4()),
                    company_id=company_id,
                    company_name=company_name,
                    mapping_config=mapping_config,
                    source_columns=source_columns,
                    confidence_score=confidence_score,
                    created_by_user_id=user_id,
                )
                db.add(new)
                return new.id

    async def get(self, company_id: str) -> Optional[Dict[str, Any]]:
        async with get_db_session() as db:
            result = await db.execute(
                select(CompanyMapping).where(CompanyMapping.company_id == company_id)
            )
            rec = result.scalar_one_or_none()
            if rec is None:
                return None
            # Touch last_used_at
            rec.last_used_at = datetime.now(timezone.utc)
            db.add(rec)
            return _to_dict(rec)

    async def get_by_id(self, mapping_id: str) -> Optional[Dict[str, Any]]:
        async with get_db_session() as db:
            result = await db.execute(
                select(CompanyMapping).where(CompanyMapping.id == mapping_id)
            )
            rec = result.scalar_one_or_none()
            return _to_dict(rec) if rec else None

    async def list_all(self) -> List[Dict[str, Any]]:
        async with get_db_session() as db:
            result = await db.execute(
                select(CompanyMapping).order_by(CompanyMapping.last_used_at.desc())
            )
            return [_to_dict(r) for r in result.scalars().all()]

    async def delete(self, mapping_id: str) -> bool:
        async with get_db_session() as db:
            result = await db.execute(
                select(CompanyMapping).where(CompanyMapping.id == mapping_id)
            )
            rec = result.scalar_one_or_none()
            if rec is None:
                return False
            await db.delete(rec)
            return True


def _to_dict(rec: CompanyMapping) -> Dict[str, Any]:
    return {
        "id":               rec.id,
        "company_id":       rec.company_id,
        "company_name":     rec.company_name,
        "mapping_config":   rec.mapping_config,
        "source_columns":   rec.source_columns,
        "confidence_score": rec.confidence_score,
        "created_at":       rec.created_at.isoformat() if rec.created_at else None,
        "last_used_at":     rec.last_used_at.isoformat() if rec.last_used_at else None,
    }
