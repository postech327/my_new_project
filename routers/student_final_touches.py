import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
import models
from utils.auth_jwt import get_current_user

router = APIRouter(
    prefix="/student/final-touches",
    tags=["student_final_touches"],
)

UNFILED_NAME = "미분류"
DIRECT_BUCKET_NAME = "기타 자료"


def _ensure_student_or_teacher(current_user: dict):
    if current_user.get("role") not in {"student", "teacher"}:
        raise HTTPException(status_code=403, detail="Permission denied")


def _record_folder_id(record: models.AnalysisRecord):
    return getattr(record, "folder_id", None) or getattr(record.passage, "folder_id", None)


def _folder_name(db: Session, folder_id):
    if folder_id is None:
        return UNFILED_NAME
    folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
    return folder.name if folder else UNFILED_NAME


def _children(db: Session, parent_id: int | None):
    query = db.query(models.Folder)
    if parent_id is None:
        query = query.filter(models.Folder.parent_id.is_(None))
    else:
        query = query.filter(models.Folder.parent_id == parent_id)
    return query.all()


def _sort_key(name: str):
    match = re.search(r"\d+", name or "")
    number = int(match.group()) if match else 9999
    return (number, name or "")


def _count_map(records):
    counts: dict[int | None, int] = {}
    for record in records:
        fid = _record_folder_id(record)
        counts[fid] = counts.get(fid, 0) + 1
    return counts


def _folder_total_count(db: Session, folder_id: int, counts: dict[int | None, int]):
    total = counts.get(folder_id, 0)
    for child in _children(db, folder_id):
        total += counts.get(child.id, 0)
    return total


def _serialize(
    record: models.AnalysisRecord,
    db: Session,
    include_detail: bool = False,
):
    passage = record.passage
    folder_id = _record_folder_id(record)
    outline = record.outline or {}
    if isinstance(outline, str):
        try:
            outline = json.loads(outline)
        except json.JSONDecodeError:
            outline = {}
    if not isinstance(outline, dict):
        outline = {}
    sentence_details = getattr(record, "sentence_details", None) or []
    if isinstance(sentence_details, str):
        try:
            sentence_details = json.loads(sentence_details)
        except json.JSONDecodeError:
            sentence_details = []
    if not isinstance(sentence_details, list):
        sentence_details = []

    data = {
        "id": record.id,
        "folder_id": folder_id,
        "folder_name": _folder_name(db, folder_id),
        "teacher_id": record.teacher_id,
        "passage_id": record.passage_id,
        "source": getattr(passage, "source_title", None) or f"Final Touch #{record.id}",
        "title_en": record.title_en,
        "title_ko": record.title_ko,
        "topic_en": record.topic_en,
        "topic_ko": record.topic_ko,
        "gist_en": record.gist_en,
        "gist_ko": record.gist_ko,
        "outline": {
            "intro": outline.get("intro", ""),
            "body": outline.get("body", ""),
            "conclusion": outline.get("conclusion", ""),
        },
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }

    if include_detail:
        data.update(
            {
                "passage": getattr(passage, "content", "") or "",
                "passage_bracketed": record.passage_bracketed,
                "sentence_details": sentence_details,
            }
        )

    return data


def _record_view(db: Session, user_id: int, record_id: int):
    view = (
        db.query(models.FinalTouchView)
        .filter(
            models.FinalTouchView.user_id == user_id,
            models.FinalTouchView.analysis_record_id == record_id,
        )
        .first()
    )
    if view:
        view.viewed_at = datetime.utcnow()
    else:
        view = models.FinalTouchView(
            user_id=user_id,
            analysis_record_id=record_id,
            viewed_at=datetime.utcnow(),
        )
        db.add(view)
    db.commit()


@router.get("")
def list_final_touches(
    limit: int = 50,
    folder_id: int | None = None,
    unfiled: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _ensure_student_or_teacher(current_user)

    records = (
        db.query(models.AnalysisRecord)
        .order_by(models.AnalysisRecord.created_at.desc(), models.AnalysisRecord.id.desc())
        .all()
    )

    if unfiled:
        records = [record for record in records if _record_folder_id(record) is None]
    elif folder_id is not None:
        records = [record for record in records if _record_folder_id(record) == folder_id]

    records = records[: min(max(limit, 1), 100)]

    return {
        "items": [_serialize(record, db) for record in records],
    }


@router.get("/folders")
def list_final_touch_folders(
    parent_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _ensure_student_or_teacher(current_user)

    records = db.query(models.AnalysisRecord).all()
    counts = _count_map(records)
    folders = _children(db, parent_id)

    items = []
    if parent_id is None and counts.get(None, 0) > 0:
        items.append(
            {
                "folder_id": None,
                "parent_id": None,
                "folder_name": UNFILED_NAME,
                "count": counts[None],
                "has_children": False,
                "is_unfiled": True,
                "is_direct_bucket": False,
            }
        )

    if parent_id is not None and counts.get(parent_id, 0) > 0:
        items.append(
            {
                "folder_id": parent_id,
                "parent_id": parent_id,
                "folder_name": DIRECT_BUCKET_NAME,
                "count": counts[parent_id],
                "has_children": False,
                "is_unfiled": False,
                "is_direct_bucket": True,
            }
        )

    for folder in folders:
        child_count = len(_children(db, folder.id))
        total = _folder_total_count(db, folder.id, counts)
        if total <= 0 and child_count <= 0:
            continue
        items.append(
            {
                "folder_id": folder.id,
                "parent_id": folder.parent_id,
                "folder_name": folder.name,
                "count": total,
                "has_children": child_count > 0,
                "is_unfiled": False,
                "is_direct_bucket": False,
            }
        )

    items.sort(key=lambda item: (item["is_unfiled"], _sort_key(item["folder_name"])))
    return {"items": items}


@router.get("/{record_id}")
def get_final_touch(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _ensure_student_or_teacher(current_user)

    record = (
        db.query(models.AnalysisRecord)
        .filter(models.AnalysisRecord.id == record_id)
        .first()
    )

    if not record:
        raise HTTPException(status_code=404, detail="Final Touch not found")

    if current_user.get("role") == "student":
        _record_view(db, int(current_user["sub"]), record.id)

    return _serialize(record, db, include_detail=True)
