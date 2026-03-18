from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader


def render_digest(
    articles: list[dict[str, Any]],
    run_stats: dict[str, Any],
    output_path: Path,
) -> Path:
    """Render articles into a Markdown digest file using Jinja2 template."""
    # Group by primary tag
    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for art in articles:
        tags = art.get("tags", [])
        primary = tags[0]["tag"] if tags else "Uncategorized"
        by_topic[primary].append(art)

    template_dir = Path("templates")
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=False,
    )

    try:
        template = env.get_template("digest.md.j2")
    except Exception:
        # Fallback: inline template
        template = env.from_string(_FALLBACK_TEMPLATE)

    now = datetime.utcnow()
    content = template.render(
        articles=articles,
        by_topic=dict(sorted(by_topic.items())),
        run_stats=run_stats,
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        date=now.strftime("%Y-%m-%d"),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


_FALLBACK_TEMPLATE = """\
# AI News Reader Digest — {{ date }}
_Generated: {{ generated_at }}_

**Run Stats:** {{ run_stats.fetched }} fetched → {{ run_stats.after_dedup }} deduped → {{ run_stats.after_filter }} kept → {{ run_stats.audited }} audited

---

{% for topic, topic_articles in by_topic.items() %}
## {{ topic }}

{% for art in topic_articles %}
### [{{ art.title }}]({{ art.url }})
_{{ art.pub_date[:10] if art.pub_date else 'Unknown date' }}_
{% if art.audit_summary %}
{{ art.audit_summary }}
{% elif art.raw_summary %}
{{ art.raw_summary[:300] }}
{% endif %}
**Tags:** {{ art.tags | map(attribute='tag') | join(', ') if art.tags else '—' }}

{% endfor %}
{% endfor %}
"""
