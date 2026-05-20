---
name: file_manager
version: 1.0.0
category: file_manager
access: production
description: Read, write, search, and manage files on the system
tags: [file, read, write, manage]
---

## File Manager Skill

When the user needs to read, write, search, or manage files:

1. Use `file_read` to read file content
2. Use `file_write` to write or update files
3. Use `command_exec` with `find`, `grep`, `ls` commands for file search
4. Always confirm paths before writing to important files
5. For large files, mention that content may be truncated