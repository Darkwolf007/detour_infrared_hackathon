# Skill: Chatbot Persona Inference via Gemini

## When to use
Only on POST /personas/custom (user selects "Custom" reason and types description).
All 13 default personas use pre-seeded Supabase rows — no Gemini needed.

## Gemini call
```python
import google.generativeai as genai
import json, re

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

SYSTEM = "You convert user descriptions into walking route weights. Return ONLY valid JSON. No markdown. No backticks. No explanation."

USER_TEMPLATE = """
User description: "{description}"
City: {city}

Return ONLY this JSON (no other text):
{{"name":"2-3 word label","w_speed":0.0,"w_shade":0.0,"w_nature":0.0,"w_discovery":0.0,
"turn_preference":"low|mid|high","default_route":"typical|multi|loop","reasoning":"one sentence"}}

Rules:
- w_speed + w_shade + w_nature + w_discovery must sum to exactly 1.0
- turn_preference: low=straight fast, mid=balanced, high=winding exploratory
- default_route: typical=A→B, multi=multiple stops, loop=circular
- City climate context:
  dubai: weight shade heavily (UTCI often 40°C+ daytime)
  chennai: weight nature+shade (hot humid, tree cover matters)
  barcelona: balanced (mild climate, good infrastructure)
"""

def infer_persona(description: str, city: str) -> dict:
    response = model.generate_content(
        [SYSTEM, USER_TEMPLATE.format(description=description, city=city)],
        generation_config={"temperature": 0.2}
    )
    raw = re.sub(r'^```json\s*|\s*```$', '', response.text.strip())
    try:
        data = json.loads(raw)
        # Validate + normalise weights
        keys = ['w_speed','w_shade','w_nature','w_discovery']
        total = sum(data[k] for k in keys)
        if abs(total - 1.0) > 0.05:
            for k in keys: data[k] = round(data[k]/total, 3)
        if data.get('turn_preference') not in ('low','mid','high'):
            data['turn_preference'] = 'mid'
        if data.get('default_route') not in ('typical','multi','loop'):
            data['default_route'] = 'typical'
        return data
    except Exception:
        return FALLBACK

FALLBACK = {
    "name":"General walker","w_speed":0.25,"w_shade":0.35,
    "w_nature":0.25,"w_discovery":0.15,
    "turn_preference":"mid","default_route":"typical",
    "reasoning":"Balanced weights used as fallback"
}
```

## Route narrative generation
```python
NARRATIVE_TEMPLATE = """
Route summary for {persona_name} in {city}:
- Distance: {distance_m}m (~{duration_min} min)
- Average UTCI: {avg_utci:.1f}°C ({comfort_rating})
- Shade coverage: {shade_pct}%
- Green cover: {nature_pct}%
- Time of day: {time_slot}

Write exactly 2 sentences explaining why this route suits this person.
Mention thermal comfort and street character. Plain text only, no markdown.
"""

def generate_narrative(meta: dict) -> str:
    r = model.generate_content(
        NARRATIVE_TEMPLATE.format(**meta),
        generation_config={"temperature": 0.4, "max_output_tokens": 100}
    )
    return r.text.strip()
```

## Frontend usage pattern
```typescript
// 1. User selects "Custom" → textarea appears
// 2. User types description (e.g. "elderly mum needs shade and coffee stops")
// 3. On "Find my route" → POST /personas/custom first
// 4. Show PersonaPreview with inferred weights
// 5. User confirms → routing proceeds with inferred weights
const inferPersona = async (description: string, city: string) => {
  const res = await fetch('/api/v1/personas/custom', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({description, city})
  })
  return (await res.json()).inferred_persona
}
```
