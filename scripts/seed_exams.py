"""Seed current exams (IBPS PO, RRB Group D) and placeholder future exams."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.database.session import create_engine, create_session_factory
from app.models.exam import Exam

CURRENT_EXAMS = [
    ("IBPS_PO", "IBPS PO", "Institute of Banking Personnel Selection — Probationary Officer"),
    ("RRB_GROUP_D", "RRB Group D", "Railway Recruitment Board — Group D"),
]

FUTURE_EXAMS = [
    ("SSC", "SSC", "Staff Selection Commission (planned)"),
    ("UPSC", "UPSC", "Union Public Service Commission (planned)"),
    ("CAT", "CAT", "Common Admission Test (planned)"),
    ("GATE", "GATE", "Graduate Aptitude Test in Engineering (planned)"),
    ("NEET", "NEET", "National Eligibility cum Entrance Test (planned)"),
    ("STATE_EXAMS", "State Exams", "Various state-level competitive exams (planned)"),
]


async def seed() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        for code, name, description in CURRENT_EXAMS + FUTURE_EXAMS:
            is_active = code in {c for c, _, _ in CURRENT_EXAMS}
            existing = await session.execute(select(Exam).where(Exam.code == code))
            if existing.scalar_one_or_none():
                print(f"skip  {code}")
                continue
            session.add(
                Exam(
                    id=uuid.uuid4(),
                    code=code,
                    name=name,
                    description=description,
                    is_active=is_active,
                )
            )
            print(f"add   {code} (active={is_active})")
        await session.commit()

    await engine.dispose()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
