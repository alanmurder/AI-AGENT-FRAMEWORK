---
name: report_generator
version: 1.0.0
category: report_generator
access: report
description: Generate professional reports, summaries, and data analysis documents
tags: [report, summary, analysis, document]
---

## Report Generator Skill

When the user needs a report or summary:

1. Clarify the report type: daily summary, weekly report, incident analysis, data report
2. Gather data using `query_database`, `file_read`, or `command_exec` as needed
3. Structure the report with clear sections: Overview, Key Findings, Details, Recommendations
4. Use `file_write` to save the report to a file
5. Use `send_notification` to notify relevant users about the report
6. For recurring reports, suggest setting up a cron schedule

## Scripts
- scripts/format_report.py — Format raw data into structured reports (Phase 2 sandbox execution)