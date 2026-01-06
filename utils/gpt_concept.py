from openai import OpenAI

client = OpenAI()

def generate_concept_by_error_type(error_type: str) -> dict:
    prompt = f"""
You are an English grammar teacher.

Create a clear grammar concept explanation for the following error type:
"{error_type}"

Return the result in JSON with the following keys:
- title_en
- title_ko
- description_en
- description_ko
- example

Rules:
- Korean explanations must be natural and student-friendly.
- The example should be a simple sentence showing correct usage.
- Do NOT include markdown.
- Return ONLY valid JSON.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful English grammar teacher."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    content = response.choices[0].message.content

    import json
    return json.loads(content)