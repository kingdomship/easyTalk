"""分析报告服务 — 里程碑自动生成 + 手动按需生成."""

from services.report.aggregator import (
    build_dashboard,
    generate_report,
    check_milestone,
    get_latest_report,
    list_reports,
    get_report_by_id,
)
