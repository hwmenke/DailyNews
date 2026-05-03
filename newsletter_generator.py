"""
newsletter_generator.py — Render the newsletter HTML from selected chart contexts.

Orchestration:
  1. Receive selected chart contexts (from story_selector) and raw series data.
  2. Compute subtitles for each chart.
  3. Generate Chart.js configs for each chart.
  4. Group charts by section.
  5. Render the Jinja2 template to an HTML file.
"""

import datetime
import json
import os
import re
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

import chart_engine as ce
from subtitle_generator import generate_subtitle, format_level, format_change
from universe import SECTION_LABELS, ALL_ASSET_CLASSES


TEMPLATES_DIR = Path(__file__).parent / "templates"


def _safe_json(obj) -> str:
    """JSON-serialize, escaping HTML-sensitive characters for safe inline use."""
    raw = json.dumps(obj, default=str)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _chart_id(label: str) -> str:
    """Convert a label to a safe HTML id string."""
    return re.sub(r"[^a-z0-9]", "-", label.lower())[:40]


def build_chart_card(ctx: dict, series: pd.Series, chart_index: int) -> dict:
    """
    Enrich a context dict with display-ready fields and generate the Chart.js config.
    Returns an augmented dict ready for template rendering.
    """
    ac       = ctx.get("asset_class", "equities")
    last     = ctx.get("last", 0)
    chg      = ctx.get("daily_chg", 0) or 0
    chg_pct  = ctx.get("daily_chg_pct")
    score    = ctx.get("interest_score", 0)
    source   = ctx.get("source", "fred")

    # Subtitle
    ctx["subtitle"] = generate_subtitle(ctx)

    # Formatted KPI values
    ctx["last_formatted"]      = format_level(last, ac)
    ctx["daily_chg_formatted"] = format_change(chg, chg_pct, ac)

    # Source label
    ctx["source_label"] = "FRED / Federal Reserve" if source == "fred" else "Yahoo Finance"

    # HTML chart id
    ctx["chart_id"] = f"c{chart_index:04d}-{_chart_id(ctx.get('label', str(chart_index)))}"

    # Chart.js config
    chart_type = ctx.get("chart_type", "line_with_context_band")
    try:
        config = ce.dispatch_chart(chart_type, series, ctx)
    except Exception:
        config = ce.line_with_context_band(series, ctx)
    ctx["chartjs_config"] = config

    return ctx


def generate_newsletter(
    selected_charts: list[dict],
    series_map: dict[str, pd.Series],
    edition_date: str | None = None,
    issue_number: int = 1,
    output_dir: str = ".",
) -> str:
    """
    Render a complete newsletter HTML file.

    Parameters
    ----------
    selected_charts : list[dict]
        Ordered list of enriched context dicts from select_stories().
    series_map : dict[str, pd.Series]
        Raw time series keyed by series id.
    edition_date : str
        ISO date string for this edition. Defaults to today.
    issue_number : int
        Sequential edition number shown in the header.
    output_dir : str
        Directory where newsletter_YYYY-MM-DD.html will be written.

    Returns
    -------
    str
        Path to the rendered HTML file.
    """
    if edition_date is None:
        edition_date = str(datetime.date.today())

    dt = datetime.date.fromisoformat(edition_date)
    weekday = dt.strftime("%A")
    edition_date_fmt = dt.strftime("%B %-d, %Y")

    # Build chart cards (enriched ctx + Chart.js config)
    enriched: list[dict] = []
    all_configs: list[dict] = []  # [{id, config}] for template
    for i, ctx in enumerate(selected_charts):
        sid = ctx.get("id", ctx.get("label", ""))
        series = series_map.get(sid, pd.Series())
        card = build_chart_card(dict(ctx), series, i)
        enriched.append(card)
        all_configs.append({
            "id":     card["chart_id"],
            "config": card["chartjs_config"],
        })

    # Group by section
    charts_by_section: dict[str, list] = {}
    for card in enriched:
        sec = card.get("asset_class", "equities")
        charts_by_section.setdefault(sec, []).append(card)

    # Section order: only include sections that have charts
    sections_present = [s for s in ALL_ASSET_CLASSES if s in charts_by_section]

    # Lead stories: top 5 by interest score
    lead_stories = sorted(enriched, key=lambda c: c.get("interest_score", 0), reverse=True)[:5]

    # Top section by chart count
    top_section = max(charts_by_section, key=lambda s: len(charts_by_section[s]),
                      default="equities").capitalize() if charts_by_section else "Markets"

    # Render Jinja2 template
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    # Pass _safe_json as a template filter
    env.filters["tojson_safe"] = _safe_json

    tmpl = env.get_template("newsletter.html")
    html = tmpl.render(
        edition_date        = edition_date_fmt,
        weekday             = weekday,
        issue_number        = issue_number,
        total_charts        = len(enriched),
        top_section         = top_section,
        lead_stories        = lead_stories,
        sections_present    = sections_present,
        section_labels      = SECTION_LABELS,
        charts_by_section   = charts_by_section,
        chart_configs_json  = _safe_json(all_configs),
        generation_timestamp= datetime.datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
    )

    # Write file
    out_dir  = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = out_dir / f"newsletter_{edition_date}.html"
    filename.write_text(html, encoding="utf-8")

    # Always update latest symlink / copy
    latest = out_dir / "newsletter_latest.html"
    latest.write_text(html, encoding="utf-8")

    return str(filename)
