# structure_analyzer.py
from typing import Optional, Any, List, Tuple

# spaCy가 환경에 없더라도 전체 앱이 죽지 않도록 보호
try:
    import spacy  # type: ignore
except Exception:
    spacy = None  # type: ignore

# Lazy singleton
_NLP: Optional[Any] = None


def _load_nlp() -> Optional[Any]:
    """
    en_core_web_sm 모델을 안전하게 로드합니다.
    - spacy가 없거나 모델이 없으면 None을 반환(상위 로직에서 우회 처리)
    """
    global _NLP
    if _NLP is not None:
        return _NLP

    if spacy is None:
        return None

    try:
        _NLP = spacy.load("en_core_web_sm")
    except Exception:
        # 배포 환경 등에서 모델이 없을 수 있음: 조용히 패스
        _NLP = None
    return _NLP


def find_full_np_span(token) -> Tuple[int, int]:
    """
    명사구 전체 범위를 대략적으로 추정해 반환.
    (left_edge ~ right_edge)
    """
    while token.dep_ not in ("nsubj", "dobj", "pobj", "attr", "nsubjpass") and token.head != token:
        token = token.head
    return token.left_edge.i, token.right_edge.i + 1


def merge_spans(spans: List[Tuple[int, int, str]]) -> List[Tuple[int, int, str]]:
    """
    오버랩 정리 + 같은 종류끼리만 병합
    spans: (start, end, kind)  where kind in ["[]", "()", "{}"]
    """
    spans = sorted(spans, key=lambda x: (x[0], -x[1]))
    merged: List[Tuple[int, int, str]] = []
    for span in spans:
        if not merged or span[0] > merged[-1][1]:
            merged.append(span)
        else:
            # 같은 종류만 병합
            if span[2] == merged[-1][2]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], span[1]), span[2])
            else:
                merged.append(span)
    return merged


def remove_overlapping_braces(spans: List[Tuple[int, int, str]]) -> List[Tuple[int, int, str]]:
    """
    중괄호("{}")는 서로 겹치지 않도록 정리 (준동사 영역이 과도하게 겹칠 때 방지)
    """
    result: List[Tuple[int, int, str]] = []
    brace_zones: List[Tuple[int, int]] = []

    for span in spans:
        if span[2] == "{}":
            overlap = False
            for bz in brace_zones:
                if not (span[1] <= bz[0] or span[0] >= bz[1]):
                    overlap = True
                    break
            if not overlap:
                brace_zones.append((span[0], span[1]))
                result.append(span)
        else:
            result.append(span)
    return result


def analyze_structure(text: str) -> str:
    """
    입력 문장을 분석하여 다음 규칙대로 괄호를 삽입한 문자열을 반환:
      - 명사절/형용사절/관계절/부사절: []
      - 형용사구/부사구(짧은 전치사구 등): ()
      - 준동사 구문(to부정사, 동명사/분사): {}
    spaCy 사용 불가 시에는 원문을 그대로 반환.
    """
    nlp = _load_nlp()
    if nlp is None:
        # 모델이 없으면 원문을 그대로 돌려줌 (API 전체 실패 방지)
        return text

    doc = nlp(text)
    spans: List[Tuple[int, int, str]] = []

    for token in doc:
        # 형용사절/관계절
        if token.dep_ in ("relcl", "acl"):
            start, end = find_full_np_span(token.head)
            spans.append((start, end, "[]"))

        # 명사절 (that/if/whether + ccomp/xcomp)
        elif token.dep_ in ("ccomp", "xcomp") and token.text.lower() in ("that", "if", "whether"):
            subtree = list(token.subtree)
            spans.append((subtree[0].i, subtree[-1].i + 1, "[]"))

        # 부사절
        elif token.dep_ == "advcl":
            subtree = list(token.subtree)
            spans.append((subtree[0].i, subtree[-1].i + 1, "[]"))

        # 짧은 전치사구는 () 로
        elif token.dep_ == "prep":
            subtree = list(token.subtree)
            if len(subtree) <= 5:
                spans.append((subtree[0].i, subtree[-1].i + 1, "()"))

        # 준동사( to + 동사 ) → {}
        elif token.text.lower() == "to" and token.head.pos_ == "VERB":
            subtree = list(token.head.subtree)
            spans.append((subtree[0].i, subtree[-1].i + 1, "{}"))

        # 분사/동명사 → {}
        elif token.tag_ in ("VBG", "VBN") and token.dep_ not in ("aux", "auxpass"):
            subtree = list(token.subtree)
            spans.append((subtree[0].i, subtree[-1].i + 1, "{}"))

    # 병합 및 중첩 중괄호 제거
    spans = merge_spans(spans)
    spans = remove_overlapping_braces(spans)

    # 토큰 단위 위치에 괄호를 삽입
    inserts: List[Tuple[int, str]] = []
    for start, end, kind in spans:
        if kind == "[]":
            inserts.append((start, "["))
            inserts.append((end, "]"))
        elif kind == "()":
            inserts.append((start, "("))
            inserts.append((end, ")"))
        elif kind == "{}":
            inserts.append((start, "{"))
            inserts.append((end, "}"))

    inserts.sort(reverse=True, key=lambda x: x[0])
    result = text
    for pos, char in inserts:
        if 0 <= pos < len(doc):
            t = doc[pos]
            result = result[:t.idx] + char + result[t.idx:]

    return result
