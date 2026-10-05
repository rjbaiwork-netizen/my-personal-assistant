from __future__ import annotations

import json
from typing import Any

from .ai_assistant import analyst_agent, report_writer_agent, scraping_agent


def run_multi_agent_workflow(topic: str, context: str = "") -> dict[str, Any]:
    scrape_plan = scraping_agent(topic)
    analysis = analyst_agent(topic, context, scrape_plan)
    report = report_writer_agent(topic, analysis)
    return {
        "topic": topic,
        "scraping_agent": scrape_plan,
        "analyst_agent": analysis,
        "report_writer_agent": report,
    }


def workflow_text(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
