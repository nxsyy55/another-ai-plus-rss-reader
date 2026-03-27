# Gemini JSON Mode — Key Constraints (ai.google.dev/gemini-api/docs/structured-output)

## Top-level schema MUST be an object
- Arrays at the top level are NOT supported
- All responses must be wrapped in a top-level object key

## Correct pattern (SDK v1.68.0)
```python
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="prompt",
    config=types.GenerateContentConfig(
        system_instruction="...",
        response_mime_type="application/json",
        max_output_tokens=2048,
    ),
)
data = json.loads(response.text)
```

## Classify fix
- WRONG: ask for `[{"article_id": N, ...}]` (bare array)
- RIGHT: ask for `{"articles": [{"article_id": N, ...}]}` (object wrapper)
