
## Addendum: announcement corroboration, source budget, lock
- **Announcement corroboration.** An official release post (https, developer's own `official_domains`) that names the same family and version, and contains every distinguishing token of a model that is already observed by another source, raises that model to `corroborated` immediately (reason "official announcement: ..."). It never creates models and never lowers verification. Models not named by a post (e.g. Gemini 4 Neon/Carbon) still wait for the 24h aggregator persistence rule.
- **Source time budget.** HuggingFace fetch has `MAX_PAGES=3` and a 20s whole-source deadline; an org is marked complete only when no further page remains.
- **Locking.** Refresh uses a transaction-scoped `pg_try_advisory_xact_lock` (key 7314202) held inside one transaction; session-level locks leak behind the Neon transaction pooler.
- **Live check (Neon-backed):** Gemini 4 Argon/Hydrogen and GPT-6.1 Sol, GPT-6.2 Astra/Sol are `corroborated` + `published` with sources [announcements, openrouter].
