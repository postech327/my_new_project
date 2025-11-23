# structure_analyzer.py
"""
문장 구조 분석기 (spaCy 없을 때도 동작하는 폴백 포함)

괄호 규칙
- [] : 절 (관계절/부사절/명사절 유사 패턴)
- () : 짧은 구 (전치사구 등)
- {} : 준동사구 (to-부정사, 분사구)

반환 형식(dict)
{
  "text": 원문,
  "analyzed_text": 괄호 삽입된 문자열,
  "spans": [ {"start": int, "end": int, "type": "adj_clause|adv_clause|noun_clause|pp|to_inf|participle"}, ... ],
  "legend": {...}
}
"""

from typing import List, Tuple, Dict, Any
import re

# ---------------------------------------------------------------------
# spaCy 로더 (없어도 동작). Python 3.13 환경이면 보통 None로 떨어짐.
# ---------------------------------------------------------------------
try:
    import spacy  # type: ignore
    _NLP = spacy.load("en_core_web_sm")
except Exception:
    _NLP = None  # 폴백 규칙 사용

# type alias
Span = Tuple[int, int, str]  # (start_char, end_char, type)

# 분류 세트
CLAUSE_TYPES = {"noun_clause", "adj_clause", "adv_clause"}
PHRASE_TYPES = {"pp", "short_phrase"}
NONFINITE_TYPES = {"to_inf", "participle"}


# ---------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------
def _priority(t: str) -> int:
    # 준동사 > 절 > 구   ← 이렇게 바꾸기
    if t in NONFINITE_TYPES:     # {"to_inf", "participle"}
        return 3
    if t in CLAUSE_TYPES:        # {"noun_clause","adj_clause","adv_clause"}
        return 2
    return 1


def _flatten_spans(spans: List[Span]) -> List[Span]:
    """
    겹치는 스팬 정리:
    - 시작 오름차순, 길이 내림차순, 우선순위 내림차순으로 정렬
    - 겹치면 우선순위 높은 것만 남김
    """
    spans = sorted(spans, key=lambda s: (s[0], -(s[1] - s[0]), -_priority(s[2])))
    out: List[Span] = []
    for s in spans:
        if not out:
            out.append(s)
            continue
        last = out[-1]
        # overlap?
        if s[0] < last[1] and s[1] > last[0]:
            if _priority(s[2]) > _priority(last[2]):
                out[-1] = s
            # 같거나 낮으면 버림
        else:
            out.append(s)
    return out


def _apply_brackets(text: str, spans: List[Span]) -> str:
    """
    스팬에 맞춰 괄호를 실제 문자열에 삽입한다.
    char index 기준으로 뒤에서부터 삽입.
    """
    inserts: List[Tuple[int, str]] = []
    for s, e, t in spans:
        if t in CLAUSE_TYPES:  # 절
            l, r = "[", "]"
        elif t in NONFINITE_TYPES:  # 준동사
            l, r = "{", "}"
        else:  # 구
            l, r = "(", ")"
        inserts.append((e, r))
        inserts.append((s, l))

    inserts.sort(reverse=True)  # 뒤에서부터 삽입
    out = list(text)
    for idx, ch in inserts:
        # idx가 범위를 벗어나는 예방
        if idx < 0:
            idx = 0
        if idx > len(out):
            idx = len(out)
        out[idx:idx] = [ch]
    return "".join(out)


# ---------------------------------------------------------------------
# spaCy 기반 분석 (환경에 있을 때만 사용됨)
#  - relcl(관계절)은 절 부분만 [ ] 처리
#  - acl(명사수식절)은 to/분사 기반이면 { }/participle가 담당하므로 스킵하여 과대범위 방지
# ---------------------------------------------------------------------
def _analyze_spacy(text: str) -> List[Span]:
    doc = _NLP(text)  # type: ignore
    spans: List[Span] = []

    def span_chars(start_token, end_token):
        return (start_token.idx, end_token.idx + len(end_token))

    for tok in doc:
        # 1) 관계절: which/who/that ... 절 부분만
        if tok.dep_ == "relcl":
            subtree = list(tok.subtree)
            s, e = span_chars(subtree[0], subtree[-1])
            spans.append((s, e, "adj_clause"))

        # 2) 명사수식절(acl)
        elif tok.dep_ == "acl":
            # to-부정사(TO)나 분사(VBG/VBN) 기반이면 {} 또는 participle 로 표현되므로 생략
            if any(t.tag_ == "TO" for t in tok.subtree) or tok.tag_ in {"VBG", "VBN"}:
                pass
            else:
                subtree = list(tok.subtree)
                s, e = span_chars(subtree[0], subtree[-1])
                spans.append((s, e, "adj_clause"))

        # 3) 부사절
        if tok.dep_ == "advcl":
            subtree = list(tok.subtree)
            s, e = span_chars(subtree[0], subtree[-1])
            spans.append((s, e, "adv_clause"))

        # 4) 명사절(ccomp)
        if tok.dep_ == "ccomp":
            subtree = list(tok.subtree)
            s, e = span_chars(subtree[0], subtree[-1])
            # 접속사가 앞에 있으면 포함
            left = subtree[0]
            if left.lower_ in {"that", "if", "whether"}:
                s = left.idx
            spans.append((s, e, "noun_clause"))

        # 5) to-부정사
        if tok.tag_ == "TO" and tok.head.pos_ == "VERB":
            head = tok.head
            subtree = list(head.subtree)
            s, e = span_chars(subtree[0], subtree[-1])
            spans.append((s, e, "to_inf"))

        # 6) 분사구
        if tok.tag_ in {"VBG", "VBN"} and tok.dep_ in {"acl", "advcl", "amod", "xcomp"}:
            subtree = list(tok.subtree)
            s, e = span_chars(subtree[0], subtree[-1])
            spans.append((s, e, "participle"))

        # 7) 전치사구(짧은)
        if tok.pos_ == "ADP" and tok.dep_ == "prep":
            subtree = list(tok.subtree)
            s, e = span_chars(subtree[0], subtree[-1])
            if (e - s) <= 40:
                spans.append((s, e, "pp"))

    return _flatten_spans(spans)


# ---------------------------------------------------------------------
# 폴백(정규식) — spaCy가 없을 때 사용 (관계절/부사절도 포착)
# ---------------------------------------------------------------------
# to-부정사 (최대 4~6어절 확장)
_TO_INF_RE = re.compile(r"\bto\s+[a-zA-Z]+(?:\s+\w+){0,5}", re.I)

# 짧은 전치사구 (PP)
_PP_RE = re.compile(
    r"\b(of|in|on|at|for|to|with|from|about|over|under|into|onto|through|without|within|between|among)\s+\w+(?:\s+\w+){0,3}\b",
    re.I,
)

# 관계절: which/who/whom/whose/that 로 시작해서 다음 쉼표·마침표·세미콜론·느낌표·물음표 전까지
_REL_CLAUSE_RE = re.compile(
    r"(?:,?\s*)\b(?:which|who(?:m)?|whose|that)\b[^.?!,;]*",
    re.I,
)

# 부사절: because/when/while/although/though/since/as/if/unless/until/once/after/before/where/whereas/so that/in order that
_ADV_CONJ_RE = re.compile(
    r"\b(?:because|when|while|although|though|since|as|if|unless|until|once|after|before|whereas|where|so that|in order that)\b[^.?!,;]*",
    re.I,
)


def _analyze_fallback(text: str) -> List[Span]:
    spans: List[Span] = []

    # 1) to-부정사
    for m in _TO_INF_RE.finditer(text):
        spans.append((m.start(), m.end(), "to_inf"))

    # 2) 짧은 전치사구
    for m in _PP_RE.finditer(text):
        spans.append((m.start(), m.end(), "pp"))

    # 3) 관계절 [which/who/that ... ,/. 까지]
    for m in _REL_CLAUSE_RE.finditer(text):
        s, e = m.start(), m.end()
        # 선행 쉼표가 붙었으면 쉼표 자체는 제외
        while s < e and text[s] in {",", " "}:
            s += 1
        if e - s >= 5:
            spans.append((s, e, "adj_clause"))

    # 4) 부사절 [because/when/... ~ ,/. 까지]
    for m in _ADV_CONJ_RE.finditer(text):
        s, e = m.start(), m.end()
        if e - s >= 5:
            spans.append((s, e, "adv_clause"))

    return _flatten_spans(spans)


# ---------------------------------------------------------------------
# 외부 노출 함수
# ---------------------------------------------------------------------
def analyze_structure(text: str) -> Dict[str, Any]:
    """
    입력 텍스트를 분석해서 괄호 삽입 문자열과 스팬 정보를 반환.
    spaCy가 있으면 의존구조 기반, 없으면 정규식 폴백 사용.
    """
    if not text or not text.strip():
        return {
            "text": text,
            "analyzed_text": text,
            "spans": [],
            "legend": {"[]": "clauses", "()": "phrases", "{}": "non-finite"},
        }

    spans = _analyze_spacy(text) if _NLP else _analyze_fallback(text)
    analyzed = _apply_brackets(text, spans)

    return {
        "text": text,
        "analyzed_text": analyzed,
        "spans": [{"start": s, "end": e, "type": t} for s, e, t in spans],
        "legend": {
            "[]": "clauses (noun/adj/adv)",
            "()": "short phrases (PP etc.)",
            "{}": "non-finite (to-inf/participle)",
        },
    }