from sqlalchemy.orm import Session
import models


def create_passage(
    db: Session,
    *,
    content: str,
    title: str | None = None,
    source: str | None = None,
    level: str | None = None,
    created_by: str | None = None,
):
    passage = models.Passage(
        title=title or "(no title)",
        content=content,
        source=source,
        level=level,
        created_by=created_by,
    )
    db.add(passage)
    db.commit()
    db.refresh(passage)
    return passage