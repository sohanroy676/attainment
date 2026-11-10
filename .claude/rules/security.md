# Security Rules (Non-negotiable)

- NEVER hardcode API keys, tokens, passwords, connection strings, or secrets directly in source files.
- Always use environment variables loaded via `.env` (or the project's config system). Commit a `.env.example` with variable names only.
- Before every commit, scan the diff for anything that looks like a secret (long random strings, "key=", "token=", "password="). If found, stop and move it to `.env` first.
- Ensure `.env`, `.env.local`, and any credentials file are listed in `.gitignore` BEFORE the first commit of a new project.
- Never log sensitive data (passwords, tokens, student names, roll numbers) to console or files. Logs and the audit log refer to students by internal id.
- **Student data:** real college workbooks stay in `data/private/` (gitignored, never read by tools). Anything that enters the repository, tests, fixtures, the demo or a chat is anonymised first (roll numbers replaced, names removed).
- **College isolation:** every tenant table has `college_id` and a row-level security policy; every query goes through the tenant manager. Never use a raw connection that bypasses them. A new table or page is not done until its isolation test exists.
- When adding a new third-party dependency, briefly check it's a real, maintained package (not a typo-squat) and that its licence is free for our use (no paid features needed) before installing.
- Validate and sanitize all external/user input on any code path that touches a database query, shell command, file path or uploaded file. Uploaded Excel files are parsed for cached values only; formulas are never evaluated.
