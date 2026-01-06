# services/passage_service.py
import hashlib
from sqlalchemy.orm import Session

from models import Passage


def calc_text_hash(text: str) -> str:
    """
    지문 내용을 기반으로 SHA256 해시를 계산.
    같은 텍스트면 항상 같은 해시 → 중복 방지에 사용.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_or_create_passage(
    db: Session,
    *,
    title: str,
    content: str,
    source: str | None = None,
    level: str | None = None,
    created_by: str | None = None,
) -> Passage:
    """
    1) content로 해시를 만들고
    2) 이미 존재하는 Passage가 있으면 그걸 리턴
    3) 없으면 새로 만들고 DB에 저장 후 리턴
    """
    text_hash = calc_text_hash(content)

    passage = db.query(Passage).filter(Passage.text_hash == text_hash).first()
    if passage:
        return passage

    passage = Passage(
        title=title,
        content=content,
        source=source,
        level=level,
        created_by=created_by,
        text_hash=text_hash,
    )
    db.add(passage)
    db.commit()
    db.refresh(passage)
    return passage