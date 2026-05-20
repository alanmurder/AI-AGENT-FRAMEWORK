---
name: database_query
version: 1.0.0
category: database_query
access: production
description: Query databases to retrieve production data, business metrics, and operational records
tags: [database, query, sql, data, production]
---

## Database Query Skill

When the user needs to query production or business data:

1. Identify the data source: production monitoring database, business metrics, operational records
2. Construct a SELECT query using `query_database`
3. Only use SELECT queries — never attempt INSERT, UPDATE, DELETE, or DROP
4. Present results in a clear, structured format (tables, summaries)
5. For complex queries, break them into steps and explain each step
6. Note: Full database integration available in Phase 2 — MVP uses placeholder responses