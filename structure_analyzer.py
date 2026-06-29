# structure_analyzer.py
"""
문장 구조 분석기 (spaCy 없을 때도 동작하는 폴백 포함)

괄호 규칙
- [] : 절 (관계절/부사절/명사절 유사 패턴)
- () : 전치사구
- {} : 구 (to-부정사, 동명사, 분사구 등)

반환 형식(dict)
{
  "text": 원문,
  "analyzed_text": 괄호 삽입된 문자열,
  "spans": [ {"start": int, "end": int, "type": str, "role": str}, ... ],
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

# 분류 세트. 기존 alias도 받아 이전 호출부와 호환한다.
CLAUSE_TYPES = {"noun_clause", "adj_clause", "adv_clause"}
PHRASE_TYPES = {
    "noun_phrase", "adj_phrase", "adv_phrase",
    "to_inf_phrase", "gerund_phrase", "participle_phrase",
    "to_inf", "participle", "short_phrase",
}
PREP_PHRASE_TYPES = {"prep_phrase", "pp"}

TYPE_ALIASES = {
    "pp": "prep_phrase",
    "to_inf": "to_inf_phrase",
    "participle": "participle_phrase",
}

TYPE_ROLES = {
    "noun_clause": "noun",
    "noun_phrase": "noun",
    "gerund_phrase": "noun",
    "adj_clause": "adjective",
    "adj_phrase": "adjective",
    "participle_phrase": "adjective",
    "adv_clause": "adverb",
    "adv_phrase": "adverb",
    "to_inf_phrase": "adverb",
    "prep_phrase": "prepositional",
}


def _canonical_type(t: str) -> str:
    return TYPE_ALIASES.get(t, t)


def _role_for_type(t: str) -> str:
    return TYPE_ROLES.get(_canonical_type(t), "adverb")


# ---------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------
def _priority(t: str) -> int:
    canonical = _canonical_type(t)
    if canonical in CLAUSE_TYPES:
        return 3
    if canonical in PHRASE_TYPES:
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
        canonical = _canonical_type(t)
        if canonical in CLAUSE_TYPES:  # 절
            l, r = "[", "]"
        elif canonical in PREP_PHRASE_TYPES:  # 전치사구
            l, r = "(", ")"
        else:  # 구
            l, r = "{", "}"
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
            first = subtree[0].lower_
            antecedent = tok.head.lemma_.lower()
            clause_type = (
                "noun_clause"
                if first == "that" and antecedent in _NOUN_THAT_ANTECEDENTS
                else "adj_clause"
            )
            spans.append((s, e, clause_type))

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
            if tok.head.tag_ == "VBG":
                continue
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
            s, e = tok.idx, subtree[-1].idx + len(subtree[-1])
            spans.append((s, e, "to_inf_phrase"))

        # 6) 분사구
        if tok.tag_ in {"VBG", "VBN"} and tok.dep_ in {"acl", "advcl", "amod", "xcomp"}:
            subtree = list(tok.subtree)
            s, e = span_chars(subtree[0], subtree[-1])
            phrase_type = (
                "gerund_phrase"
                if tok.tag_ == "VBG"
                and tok.head.lemma_.lower()
                in {"include", "involve", "require", "consider"}
                else "participle_phrase"
            )
            spans.append((s, e, phrase_type))

        # 7) 전치사구(짧은)
        if tok.pos_ == "ADP" and tok.dep_ in {"prep", "agent"}:
            subtree = list(tok.subtree)
            s, e = span_chars(subtree[0], subtree[-1])
            if (e - s) <= 40:
                spans.append((s, e, "prep_phrase"))

    return _flatten_spans(spans)


# ---------------------------------------------------------------------
# 폴백(정규식) — spaCy가 없을 때 사용 (관계절/부사절도 포착)
# ---------------------------------------------------------------------
# to-부정사 (최대 4~6어절 확장)
_TO_INF_START_RE = re.compile(r"\bto\s+([a-zA-Z]+)\b", re.I)

# 동명사구: 목적어 자리에 자주 오는 -ing 구문만 보수적으로 감지
_GERUND_AFTER_VERB_RE = re.compile(
    r"\b(?:include|includes|included|involve|involves|required?|requires|consider|considers)\s+"
    r"(?P<gerund>[a-zA-Z]+ing)\b",
    re.I,
)

# 짧은 전치사구 (PP)
_PREPOSITIONS = {
    "of", "in", "on", "at", "for", "to", "by", "with", "from", "about",
    "over", "under", "into", "onto", "through", "toward", "towards",
    "without", "within", "between", "among",
}
_PREP_START_RE = re.compile(
    rf"\b(?:{'|'.join(sorted(_PREPOSITIONS, key=len, reverse=True))})\b",
    re.I,
)

# 관계절: which/who/whom/whose/that 로 시작해서 다음 쉼표·마침표·세미콜론·느낌표·물음표 전까지
# Final Touch rule:
# Relative clauses are bracketed without including the antecedent.
# Example: the students [who tried ...], not [the students who tried ...].
_REL_CLAUSE_START_RE = re.compile(r"\b(?:which|who(?:m)?|whose|that)\b", re.I)
_WORD_RE = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)?")
_AUXILIARIES = {
    "am", "are", "is", "was", "were", "be", "been", "being",
    "can", "could", "do", "does", "did", "had", "has", "have",
    "may", "might", "must", "shall", "should", "will", "would",
}
_COMMON_FINITE_VERBS = {
    "assume", "assumes", "create", "creates", "created", "fail", "fails",
    "failed", "suggest", "suggests", "support", "supports", "supported",
    "want", "wants", "wanted", "believe", "believes", "believed",
    "lay", "lays", "laid", "move", "moves", "moved", "share", "shares",
    "shared",
}
_NOUN_THAT_ANTECEDENTS = {
    "idea", "fact", "belief", "claim", "notion", "possibility", "thought",
    "evidence", "report", "argument", "assumption", "view",
}
_NON_VERBAL_TO_TARGETS = {
    "a", "an", "the", "people", "students", "perfume", "perfumes",
    "messages", "study", "animals", "characteristics",
}
_PARTICIPLE_RE = re.compile(
    r"\b(?:given|based|used|made|known|written|called|designed|created|provided|related|associated|included|located|shown|taken|built|found|considered|selected|required|combined|compared|derived|intended|attached|connected|published|measured|observed|reported)\b"
    r"(?:\s+(?:to|by|with|for|from|in|on|at|of)\s+[a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})?",
    re.I,
)

# 부사절: because/when/while/although/though/since/as/if/unless/until/once/after/before/where/whereas/so that/in order that
_ADV_CONJ_RE = re.compile(
    r"\b(?:because|when|while|although|though|since|as|if|unless|until|once|after|before|whereas|where|so that|in order that)\b[^.?!,;]*",
    re.I,
)


def _sentence_fragment_end(text: str, start: int) -> int:
    match = re.search(r"[,;.!?]", text[start:])
    return start + match.start() if match else len(text)


def _rstrip_span_end(text: str, start: int, end: int) -> int:
    while end > start and text[end - 1].isspace():
        end -= 1
    return end


def _trim_clause_end(text: str, content_start: int) -> int:
    """
    Stop a fallback clause before a likely next main predicate.

    The fallback is intentionally conservative: readable brackets are more
    useful for Final Touch than an overlong clause capture.
    """
    limit = _sentence_fragment_end(text, content_start)
    words = list(_WORD_RE.finditer(text, content_start, limit))
    predicate_seen = False
    words_after_predicate = 0

    for index, word_match in enumerate(words):
        word = word_match.group(0).lower()
        previous = words[index - 1].group(0).lower() if index else ""
        looks_like_predicate = (
            word in _AUXILIARIES
            or word in _COMMON_FINITE_VERBS
            or word.endswith("ed")
            or word.endswith("ing")
        )
        starts_next_predicate = (
            predicate_seen
            and words_after_predicate >= 1
            and previous
            not in {"to", "has", "have", "had", "is", "are", "was", "were"}
            and (
                word in _AUXILIARIES
                or word in _COMMON_FINITE_VERBS
                or word.endswith("ed")
            )
        )
        if starts_next_predicate:
            return _rstrip_span_end(text, content_start, word_match.start())
        if looks_like_predicate and not predicate_seen:
            predicate_seen = True
        elif predicate_seen:
            words_after_predicate += 1

    return _rstrip_span_end(text, content_start, limit)


def _iter_to_infinitive_spans(text: str):
    for match in _TO_INF_START_RE.finditer(text):
        first_word = match.group(1).lower()
        if (
            first_word in _NON_VERBAL_TO_TARGETS
            or first_word.endswith("s")
            or first_word.endswith("ed")
            or first_word.endswith("ing")
        ):
            continue

        limit = _sentence_fragment_end(text, match.start())
        words = list(_WORD_RE.finditer(text, match.start(), limit))
        if len(words) < 2:
            continue

        end = words[1].end()
        for word_match in words[2:7]:
            word = word_match.group(0).lower()
            if (
                word == "to"
                or word in _AUXILIARIES
                or word in _COMMON_FINITE_VERBS
                or word.endswith("ed")
            ):
                break
            end = word_match.end()
        yield match.start(), end, "to_inf_phrase"


def _iter_relative_or_that_clause_spans(text: str):
    for match in _REL_CLAUSE_START_RE.finditer(text):
        end = _trim_clause_end(text, match.end())
        if end - match.start() < 5:
            continue

        clause_type = "adj_clause"
        if match.group(0).lower() == "that":
            before = list(_WORD_RE.finditer(text, 0, match.start()))
            antecedent = before[-1].group(0).lower() if before else ""
            if (
                antecedent in _NOUN_THAT_ANTECEDENTS
                or antecedent in _COMMON_FINITE_VERBS
            ):
                clause_type = "noun_clause"
        yield match.start(), end, clause_type


def _iter_participle_spans(text: str):
    for match in _PARTICIPLE_RE.finditer(text):
        before = list(_WORD_RE.finditer(text, 0, match.start()))
        previous = before[-1].group(0).lower() if before else ""
        if previous in _AUXILIARIES:
            continue
        end = match.end()
        for word_match in _WORD_RE.finditer(text, match.start(), end):
            if (
                word_match.start() > match.start()
                and word_match.group(0).lower() in _COMMON_FINITE_VERBS
            ):
                end = word_match.start()
                break
        end = _rstrip_span_end(text, match.start(), end)
        yield match.start(), end, "participle_phrase"


def _iter_gerund_phrase_spans(text: str):
    for match in _GERUND_AFTER_VERB_RE.finditer(text):
        start = match.start("gerund")
        limit = _sentence_fragment_end(text, start)
        words = list(_WORD_RE.finditer(text, start, min(limit + 1, len(text))))
        if len(words) < 2:
            continue

        end = words[0].end()
        for word_match in words[1:12]:
            word = word_match.group(0).lower()
            if word in _AUXILIARIES or word in _COMMON_FINITE_VERBS:
                break
            end = word_match.end()
        yield start, end, "gerund_phrase"


def _iter_prep_phrase_spans(text: str):
    for match in _PREP_START_RE.finditer(text):
        limit = _sentence_fragment_end(text, match.start())
        words = list(
            _WORD_RE.finditer(text, match.start(), min(limit + 1, len(text)))
        )
        if len(words) < 2:
            continue

        end = words[1].end()
        for word_match in words[2:5]:
            word = word_match.group(0).lower()
            if (
                word in _PREPOSITIONS
                or word in _AUXILIARIES
                or word in _COMMON_FINITE_VERBS
                or word.endswith("ed")
                or word.endswith("ing")
            ):
                break
            end = word_match.end()
        yield match.start(), end, "prep_phrase"


def _analyze_fallback(text: str) -> List[Span]:
    spans: List[Span] = []

    # 1) to-부정사
    spans.extend(_iter_to_infinitive_spans(text))

    # 2) 짧은 전치사구
    spans.extend(_iter_prep_phrase_spans(text))

    # 3) 관계절 [which/who/that ... ,/. 까지]
    for s, e, t in _iter_relative_or_that_clause_spans(text):
        # 선행 쉼표가 붙었으면 쉼표 자체는 제외
        while s < e and text[s] in {",", " "}:
            s += 1
        if e - s >= 5:
            spans.append((s, e, t))

    # 4) 부사절 [because/when/... ~ ,/. 까지]
    for m in _ADV_CONJ_RE.finditer(text):
        s, e = m.start(), m.end()
        if e - s >= 5:
            spans.append((s, e, "adv_clause"))

    # 5) Common reduced participle phrases used in reading passages.
    spans.extend(_iter_participle_spans(text))

    # 6) Common object-position gerund phrases.
    spans.extend(_iter_gerund_phrase_spans(text))

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
            "legend": {
                "[]": "clauses",
                "{}": "phrases",
                "()": "prepositional phrases",
            },
        }

    spans = _analyze_spacy(text) if _NLP else _analyze_fallback(text)
    analyzed = _apply_brackets(text, spans)

    return {
        "text": text,
        "analyzed_text": analyzed,
        "spans": [
            {
                "start": s,
                "end": e,
                "type": _canonical_type(t),
                "role": _role_for_type(t),
            }
            for s, e, t in spans
        ],
        "legend": {
            "[]": "clauses (noun/adj/adv)",
            "{}": "phrases (noun/adj/adv/non-finite)",
            "()": "prepositional phrases",
        },
    }
