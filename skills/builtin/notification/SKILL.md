---
name: notification
version: 1.0.0
category: notification
access: production
description: Send notifications, alerts, and messages to users via different channels
tags: [notification, alert, message, channel]
---

## Notification Skill

When the user needs to send alerts or notifications:

1. Determine the notification type: alert, reminder, report, status update
2. Choose appropriate channel: web (immediate), dingtalk (team), feishu (collaboration)
3. Use `send_notification` to deliver the message
4. For urgent alerts, mention severity level and required action
5. Log notification in memory for tracking