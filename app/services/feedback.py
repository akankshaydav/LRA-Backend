"""AI feedback. Uses Claude if ANTHROPIC_API_KEY is set; otherwise rule-based tips."""
import json
import logging

from ..config import settings

log = logging.getLogger(__name__)

TIPS = {
    "shallow_squat": "Squat depth was often too shallow — aim for thighs parallel to the floor.",
    "knee_valgus": "Your knees drifted inward — push them out over your toes.",
    "rounded_back": "Keep your chest up and back neutral during each rep.",
    "arms_low": "Raise your arms fully overhead on jumping jacks.",
}


def _rule_based(score: int, duration: float, exercises: dict, form_errors: dict) -> str:
    parts = [f"Nice work! You scored {score} in {round(duration / 60, 1)} min."]
    if exercises:
        parts.append("Reps: " + ", ".join(f"{k.replace('_', ' ')} ×{v}" for k, v in exercises.items()) + ".")
    for err, _count in sorted(form_errors.items(), key=lambda kv: -kv[1])[:2]:
        parts.append(TIPS.get(err, f"Watch your form: {err.replace('_', ' ')}."))
    if not form_errors:
        parts.append("Form looked solid throughout — try increasing difficulty next time.")
    return " ".join(parts)


def generate_feedback(score: int, duration: float, exercises: dict, form_errors: dict) -> str:
    fallback = _rule_based(score, duration, exercises, form_errors)
    if not settings.anthropic_api_key:
        return fallback
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=8.0)
        data = json.dumps({"score": score, "duration_sec": duration,
                           "reps": exercises, "form_errors": form_errors})
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=250,
            system="You are an encouraging fitness coach inside a family TV game. "
                   "Given session stats as JSON, write 2-3 short sentences: praise, "
                   "one concrete form tip based on form_errors, one next-step goal. No medical advice.",
            messages=[{"role": "user", "content": data}],
        )
        return msg.content[0].text.strip() or fallback
    except Exception as e:  # never fail a save because feedback failed
        log.warning("AI feedback failed: %s", e)
        return fallback
