import spacy

nlp = spacy.load("en_core_web_sm")

def find_full_np_span(token):
    while token.dep_ not in ("nsubj", "dobj", "pobj", "attr", "nsubjpass") and token.head != token:
        token = token.head
    return token.left_edge.i, token.right_edge.i + 1

def merge_spans(spans):
    spans = sorted(spans, key=lambda x: (x[0], -x[1]))
    merged = []
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

def remove_overlapping_braces(spans):
    result = []
    brace_zones = []

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

def analyze_structure(text: str):
    doc = nlp(text)
    spans = []

    for token in doc:
        if token.dep_ in ("relcl", "acl"):
            start, end = find_full_np_span(token.head)
            spans.append((start, end, "[]"))
        elif token.dep_ in ("ccomp", "xcomp") and token.text.lower() in ("that", "if", "whether"):
            subtree = list(token.subtree)
            spans.append((subtree[0].i, subtree[-1].i + 1, "[]"))
        elif token.dep_ == "advcl":
            subtree = list(token.subtree)
            spans.append((subtree[0].i, subtree[-1].i + 1, "[]"))
        elif token.dep_ == "prep":
            subtree = list(token.subtree)
            if len(subtree) <= 5:
                spans.append((subtree[0].i, subtree[-1].i + 1, "()"))
        elif token.text == "to" and token.head.pos_ == "VERB":
            subtree = list(token.head.subtree)
            spans.append((subtree[0].i, subtree[-1].i + 1, "{}"))
        elif token.tag_ in ("VBG", "VBN") and token.dep_ not in ("aux", "auxpass"):
            subtree = list(token.subtree)
            spans.append((subtree[0].i, subtree[-1].i + 1, "{}"))

    # 병합 및 중첩 중괄호 제거
    spans = merge_spans(spans)
    spans = remove_overlapping_braces(spans)

    inserts = []
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

    inserts.sort(reverse=True)
    result = text
    for pos, char in inserts:
        if pos < len(doc):
            token = doc[pos]
            result = result[:token.idx] + char + result[token.idx:]

    return result