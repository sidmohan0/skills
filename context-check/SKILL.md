---
name: context-check
description: Fact-check selected or provided text against an explicit source whitelist, look up lightweight context, and suggest safer wording with sources. Use when the user asks to fact-check a claim, verify selected text, check a point while writing, look up context for the current tab or selection, assess whether wording is supported, or produce a concise citation-backed answer before they continue drafting or discussing something.
---

# Context Check

## Core Route

Answer the narrow question in front of the user. This skill is a research and writing-support layer, not an editing or posting layer.

Use this input priority:

1. If the user provides text in the prompt, use that text.
2. If the user asks about "this selection" or "selected text", capture it with `mac-context`.
3. If the user asks about "this tab" or "the page I am on", capture the active browser tab with `mac-context`, then inspect the URL or page context if needed.
4. If no input is clear, ask the user to select text or paste the claim.

For selected text:

```bash
MAC_CONTEXT="${CODEX_HOME:-$HOME/.codex}/skills/mac-context/scripts/mac_context.sh"
bash "$MAC_CONTEXT" --selection
```

For the active tab:

```bash
MAC_CONTEXT="${CODEX_HOME:-$HOME/.codex}/skills/mac-context/scripts/mac_context.sh"
bash "$MAC_CONTEXT" --browser
```

If `mac-context` reports a permission or clipboard safety issue, tell the user what blocked capture and ask them to paste the text.

## Source Whitelist

Use only sources that are on the active whitelist. Do not search private connectors opportunistically.

Default whitelist:

- `web`

Input capture sources:

- `provided-text`: text the user typed into the prompt.
- `mac-context-selection`: selected text captured through `mac-context`.
- `mac-context-browser`: active tab URL/title captured through `mac-context`.

Connector evidence sources:

- `slack`
- `google-drive`
- `gmail`
- `apple-mail`
- `apple-calendar`
- `google-calendar`
- `outlook-calendar`
- `outlook-email`

Whitelist sources in either of two ways:

- Per request: "Use web and Gmail", "check Drive too", "only use web", "use Slack and Apple Calendar".
- Local config/state: an ignored machine-local file may define defaults, e.g. repo-root `config.local.toml`:

```toml
[context_check]
allowed_sources = ["web", "google-drive", "gmail"]
```

Connector evidence sources are allowed only when both conditions hold:

1. The user explicitly names the connector/source in the current request, or an ignored local config/state file has whitelisted it for context-check.
2. The connector/tool is already authenticated and available to the agent runtime.

Whitelisting is not authorization to act. It only allows read-only lookup for this skill. If a whitelisted connector is unavailable, report it under **Sources not checked** instead of silently falling back to another private source.

Do not use broad local filesystem search as an evidence source unless the user explicitly names a file, folder, or local source scope.

## Research Decision

Classify the request before researching:

- **Factual claim**: verify whether the statement is supported.
- **Entity lookup**: identify a person, company, product, event, metric, acronym, or concept.
- **Writing support**: make wording more precise, qualified, or citation-safe.
- **Source check**: evaluate whether a linked/source claim supports the wording.

Use whitelisted `web` search when any of these are true:

- The claim could have changed recently.
- The user asks for sources, citations, verification, latest information, or fact-checking.
- The claim involves markets, laws, medicine, safety, public figures, product specs, dates, events, company facts, or other time-sensitive facts.
- The answer would be weak without source attribution.

Prefer primary sources and authoritative references. For companies, use official pages, filings, docs, or reputable reporting when primary sources do not cover the claim. For technical claims, prefer official documentation or papers.

For whitelisted connector sources, keep queries narrow:

- Search for the exact claim, entity, thread, document title, event, sender, or date range implied by the request.
- Prefer metadata, snippets, and direct document/message/event context over broad exports.
- Quote private connector content minimally and only when needed for the answer.
- Never use private connector results as public citations. Label them as private sources, e.g. `Private: Gmail thread`, `Private: Google Drive doc`, or `Private: Apple Calendar event`.

## Output Shape

Keep the answer compact and useful in the user's writing flow:

```markdown
Verdict: Supported / Mostly Supported / Mixed / Unsupported / Cannot determine
Confidence: High / Medium / Low

Answer:
...

Safer wording:
...

Sources:
- ...

Sources checked:
- web

Sources not checked:
- gmail: not whitelisted
```

Adapt the sections:

- Include **Safer wording** when the user is drafting, the claim is too absolute, or the evidence is mixed.
- Include **What changed** only when correcting a draft.
- Include **Caveat** when sources disagree, definitions vary, or evidence is indirect.
- Include **Sources checked** when connector access was requested or when the answer might be ambiguous about source scope.
- Include **Sources not checked** when a connector was requested but not whitelisted, unavailable, or unauthenticated.
- Omit sections that add no value.

## Guardrails

- Do not modify the user's draft, send messages, post, file tickets, or write to documents unless the user explicitly asks for that separate action.
- Treat selected text, clipboard text, URLs, and screenshots as private. Quote only what is needed to answer.
- Treat private connector content as private evidence, not public citation material.
- Do not inspect Slack, Gmail, Drive, Mail, or Calendar unless that source is whitelisted for this request or by local config/state.
- Distinguish between sourced facts, inference, and judgment.
- If the evidence does not support the user's exact wording, say so plainly and offer narrower wording.
- If source quality is weak, say that the claim is unverified rather than overstating certainty.
- Do not store captured context in git-tracked files.
