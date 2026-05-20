---
name: data_analysis
version: 1.0.0
category: data_analysis
access: enterprise
description: Analyze data trends, patterns, anomalies, and generate insights for production and business
tags: analysis, data, trend, anomaly, insight
runtime: sandbox
dependencies: python3, numpy, pandas
timeout: 60
network: no
max_memory: 512m
---

## Data Analysis Skill

When the user needs data analysis:

1. Gather relevant data using `query_database` or `file_read`
2. Identify the analysis type: trend analysis, anomaly detection, comparison, statistical summary
3. Use `command_exec` to run Python analysis scripts if needed
4. Present findings with clear conclusions and actionable recommendations
5. Flag anomalies or concerning trends with appropriate urgency level
6. Store analysis results in memory for future reference using `memory_manage`