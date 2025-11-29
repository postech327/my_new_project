# services/gpt_prompts.py
"""
각 question_type(topic/title/gist/summary/cloze/insertion/order/all)에 맞는
프롬프트를 만들어주는 모듈.
모든 유형은 같은 JSON 형식으로 응답하도록 요구한다.
"""

from textwrap import dedent


def _json_spec() -> str:
    """GPT에게 항상 요구할 공통 JSON 포맷 설명."""
    return dedent(
        """
        Return ONLY valid JSON with the following structure:

        [
          {
            "question_type": "topic",  // or title/gist/summary/cloze/insertion/order
            "stem": "question text in English",
            "options": [
              {"label": "①", "text": "option text", "is_correct": false},
              {"label": "②", "text": "option text", "is_correct": true},
              {"label": "③", "text": "option text", "is_correct": false},
              {"label": "④", "text": "option text", "is_correct": false},
              {"label": "⑤", "text": "option text", "is_correct": false}
            ],
            "correct_option_label": "②"
          }
        ]
        """
    )


# ───────────────── topic: 중심 생각 ─────────────────
def prompt_topic(passage: str, num_questions: int) -> str:
    return dedent(
        f"""
        You are an expert English CSAT problem maker.

        Passage:
        \"\"\"{passage}\"\"\"


        Task:
        Create {num_questions} multiple-choice questions that ask for
        the **topic (central idea)** of the passage.

        • Use the instruction sentence:
          "Which of the following is best for the topic of the passage?"
        • Make 5 choices using circled digits: ① ② ③ ④ ⑤.
        • Choices should be short noun-phrases or short clauses.
        • Try NOT to use the exact same wording from the passage.
        • Provide exactly one correct answer for each question.

        {_json_spec()}
        """
    )


# ───────────────── title: 제목 ─────────────────
def prompt_title(passage: str, num_questions: int) -> str:
    return dedent(
        f"""
        You are an expert English CSAT problem maker.

        Passage:
        \"\"\"{passage}\"\"\"


        Task:
        Create {num_questions} multiple-choice questions that ask for
        the **best title** of the passage.

        • Use the instruction sentence:
          "Which of the following is best for the title of the passage?"
        • Make 5 choices using circled digits: ① ② ③ ④ ⑤.
        • Choices should sound like natural titles.
        • Try NOT to copy phrases directly from the passage.
        • Provide exactly one correct answer for each question.

        {_json_spec()}
        """
    )


# ───────────────── gist: 요지 ─────────────────
def prompt_gist(passage: str, num_questions: int) -> str:
    return dedent(
        f"""
        You are an expert English CSAT problem maker.

        Passage:
        \"\"\"{passage}\"\"\"


        Task:
        Create {num_questions} multiple-choice questions that ask for the **gist**
        (what the writer is trying to say).

        • Prefer the instruction:
          "What is the writer trying to say?"
        • If needed, you may also use:
          "Which of the following is the main idea of the passage?"
        • Choices MUST be full sentences.
        • Make 5 choices using circled digits: ① ② ③ ④ ⑤.
        • Try not to use exactly the same sentences as in the passage.
        • Provide exactly one correct answer for each question.

        {_json_spec()}
        """
    )


# ───────────────── summary: 요약 ─────────────────
def prompt_summary(passage: str, num_questions: int) -> str:
    return dedent(
        f"""
        You are an expert English CSAT problem maker.

        Passage:
        \"\"\"{passage}\"\"\"


        Task:
        For each question:
        1. First, summarize the passage in ONE sentence in English.
           Try NOT to use the same wording as the passage.
        2. Make 4 additional distractor sentences.
        3. Then create an MCQ:

           "Which of the following best summarizes the passage?"

        • 5 choices with circled digits: ① ② ③ ④ ⑤.
        • Exactly one correct summary, four plausible but incorrect summaries.

        {_json_spec()}
        """
    )


# ───────────────── cloze: 빈칸 추론 ─────────────────
def prompt_cloze(passage: str, num_questions: int) -> str:
    """
    빈칸 정답 = 지문의 '중심 소재' 혹은 핵심 의미 단위.
    - 단어 하나일 수도 있고,
    - 명사구 / 명사절 / 형용사구 / 형용사절일 수도 있음.
    - 원문과 완전히 같은 단어가 아니어도 되며,
      Lexile 난이도에 맞는 유의어·동등 표현도 허용.
    """
    return dedent(
        f"""
        You are an expert English CSAT problem maker.

        Passage:
        \"\"\"{passage}\"\"\"


        Task:
        Create {num_questions} **cloze (blank-filling)** questions.

        Central idea rule (very important):

        • First, identify the central idea or key conceptual element of the passage.
          This could be expressed as a single word (e.g. "thought"),
          a noun phrase, a noun clause, or an adjectival/adverbial phrase.
        • If this central idea appears in more than one sentence,
          choose the sentence where it plays the most important logical role
          in the flow of the passage.
        • The blank you create must target this central idea.

        For each question:

        1. Select or slightly rewrite ONE sentence from the passage so that:
           - Its meaning is unchanged.
           - It clearly expresses the central idea.
        2. Replace the central idea word/phrase/clause with a blank (____).
        3. Use the instruction:
           "Which of the following is best for the blank?"
        4. Create 5 answer choices (①~⑤) that are all grammatically possible,
           BUT only ONE is logically and contextually correct.

           The correct option may be:
           - the exact original word from the passage,
           - OR a close synonym,
           - OR an equivalent noun phrase, noun clause,
             adjectival phrase, or adverbial phrase
             that preserves the same meaning and level of abstraction.

        5. Distractors must:
           - fit grammatically into the blank,
           - be related in theme, but
           - distort or miss the key meaning so that they are incorrect.

        6. Avoid reusing the exact same expression from the passage
           in the incorrect options.

        {_json_spec()}
        """
    )


# ───────────────── insertion: 문장 삽입 ─────────────────
def prompt_insertion(passage: str, num_questions: int) -> str:
    """
    삽입형:
    - 원문에 있는 문장만 사용 (의미 변경, 패러프레이즈 금지).
    - 길이 때문에 필요한 경우 문장을 둘로 쪼갤 수는 있음.
    - 학생 화면에서는 '원문 전체'를 보여주지 않고,
      stem 안에 '삽입할 문장 + (①)~(⑤) 표시가 들어간 본문'만 사용하게 될 것.
    """
    return dedent(
        f"""
        You are an expert English CSAT problem maker.

        Passage:
        \"\"\"{passage}\"\"\"


        Task:
        Create {num_questions} **sentence insertion** questions.

        STRICT CONTENT RULES (very important):

        • Use ONLY sentences from the original passage.
        • You may split a long sentence into two shorter sentences
          or adjust punctuation, BUT:
          - Do NOT paraphrase.
          - Do NOT invent new content.
          - Do NOT change the meaning of any sentence.
        • The resulting question must still be fully faithful
          to the original passage.

        For each question:

        1. Choose ONE key sentence from the passage
           that expresses an important idea.
           This becomes the "sentence to insert".

        2. Take the original passage and mark possible insertion points as:
             (①), (②), (③), (④), (⑤)
           - Use at most five insertion points.
           - Place (①)~(⑤) in natural, grammatically valid boundaries
             between sentences or clauses.

        3. Use the instruction:
           "Where would the following sentence best fit in the passage?"

        4. In the stem, include BOTH of the following in a clear format:
           - First, the sentence to insert, clearly separated.
           - Then, the passage with (①)~(⑤) markers embedded in it.
             Make sure there are line breaks so that the passage is readable.

        5. Provide answer choices:
           ① ② ③ ④ ⑤
           (They simply refer to positions (①)~(⑤) in the passage.)

        6. There must be EXACTLY one correct insertion point where:
           - the logical flow of ideas is best,
           - referents (pronouns, conjunctions, etc.) are clear.

        {_json_spec()}
        """
    )


# ───────────────── order: 문단 순서 배열 ─────────────────
def prompt_order(passage: str, num_questions: int) -> str:
    """
    순서 배열:
    - 주어진 부분 + (A)(B)(C) 3개 단락.
    - (A)(B)(C)는 원문에서만 문장을 가져오고, 의미/내용은 바꾸지 않음.
    - (A)(B)(C) 앞에는 반드시 한 줄씩 띄워서 단락이 분리되도록 함.
    """
    return dedent(
        f"""
        You are an expert English CSAT problem maker.

        Passage (a single long paragraph or a few connected sentences):
        \"\"\"{passage}\"\"\"


        Task:
        Create {num_questions} **paragraph ordering** questions with three parts (A), (B), (C).

        STRICT CONTENT RULES (very important):

        1. Split the original passage into:
           - a GIVEN first part (one or two sentences) that will come first, and
           - three meaningful paragraphs (A), (B), (C).

        2. Use ONLY sentences from the original passage for the GIVEN part and (A)(B)(C).
           - You may split a long sentence into two shorter ones,
             or adjust punctuation,
             BUT you must NOT paraphrase, invent, or change meaning.
           - Do NOT create new information that was not in the original passage.

        3. Paragraph lengths should be similar
           and each paragraph should be coherent on its own.

        LAYOUT RULES (very important):

        In the "stem" field, write the question text in this order and format:

        1. Korean instruction sentence:
           "주어진 글 다음에 이어질 글의 순서로 가장 적절한 것을 고르시오."

        2. One blank line.

        3. The GIVEN first part (one or two sentences) that comes BEFORE (A)(B)(C).

        4. One blank line.

        5. Then write the three paragraphs using EXACTLY this visual format
           with blank lines between them:

           (A) Sentence(s) for paragraph A...

           (B) Sentence(s) for paragraph B...

           (C) Sentence(s) for paragraph C...

           • There must be a blank line BEFORE each of (A), (B), and (C),
             so that they appear as clearly separated paragraphs,
             just like Korean CSAT examples.

        ORDERING & OPTIONS:

        1. Choose one correct order among:
             (A)-(C)-(B),
             (B)-(A)-(C),
             (B)-(C)-(A),
             (C)-(A)-(B),
             (C)-(B)-(A).

        2. In the JSON, "correct_option_label" must be one of:
             "①", "②", "③", "④", "⑤",
           corresponding to the above five orders in that exact sequence.

        3. In the JSON "stem", include:
           - the Korean instruction sentence,
           - the GIVEN first part,
           - and (A)(B)(C) in the scrambled order you actually used
             for this particular question.

        {_json_spec()}
        """
    )


# ───────────────── all / default ─────────────────
def prompt_default_all(passage: str, num_questions: int) -> str:
    """question_type = 'all' 이거나 알 수 없을 때 기본 MCQ 생성."""
    return dedent(
        f"""
        You are an expert English CSAT problem maker.

        Passage:
        \"\"\"{passage}\"\"\"


        Task:
        Create {num_questions} high-quality multiple-choice questions about
        the passage (a mixture of topic/title/gist/summary/cloze types is allowed).

        • Each question should be clearly labeled by "question_type"
          among: "topic", "title", "gist", "summary", "cloze".
        • Follow Korean CSAT style.
        • Use 5 choices with circled digits ① ② ③ ④ ⑤.
        • Provide exactly one correct answer for each.

        {_json_spec()}
        """
    )


# ───────────────── dispatcher ─────────────────
def build_prompt(question_type: str, passage: str, num_questions: int) -> str:
    """
    외부에서 부를 때 쓰는 통합 함수.

    question_type: 'topic' | 'title' | 'gist' | 'summary'
                   | 'cloze' | 'insertion' | 'order' | 'all'
    """
    qtype = (question_type or "all").lower()

    if qtype == "topic":
        return prompt_topic(passage, num_questions)
    if qtype == "title":
        return prompt_title(passage, num_questions)
    if qtype == "gist":
        return prompt_gist(passage, num_questions)
    if qtype == "summary":
        return prompt_summary(passage, num_questions)
    if qtype == "cloze":
        return prompt_cloze(passage, num_questions)
    if qtype == "insertion":
        return prompt_insertion(passage, num_questions)
    if qtype == "order":
        return prompt_order(passage, num_questions)

    # "all" 또는 알 수 없는 값 → 기본 믹스형
    return prompt_default_all(passage, num_questions)