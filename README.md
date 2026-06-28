# Skills

Reusable local skills for Codex-first computer-use workflows.

This repository is currently built around Codex as the primary agent runtime. The skill format, install path, and connector assumptions are Codex-oriented today. Over time, the goal is to keep the underlying workflows portable so other local agent harnesses can reuse the same deterministic scripts, permission model, and skill instructions.

## Layout

- `CHARTER.md` is the shared safety charter every skill inherits.
- `mac-context/` is the read-mostly "eyes" foundation for local macOS context.
- `context-check/` fact-checks selected or provided text with sources.
- `daily-inbox-view/` previews and triages Apple Mail inboxes.
- `daily-calendar-view/` builds a read-only daily calendar agenda from connected calendar sources.

## Vision

These skills are growing into a local-first personal assistant, one capability
at a time: eyes, ears/voice, hands, and memory. Every skill follows the shared
rules in `CHARTER.md`: deterministic interfaces first, read-mostly defaults,
explicit named-target consent for actions, source systems as truth, and no
private context in git.

## Included Skills

### `mac-context`

Purpose: observe the local macOS session before an agent acts.

What it can do:

- Report the frontmost app and front window title.
- Read the active browser tab, or browser tabs across browser windows.
- Read the text clipboard.
- Capture the current text selection by issuing Cmd+C, then restore the prior
  text clipboard.
- Take screenshots for vision-based interpretation of non-scriptable UI.
- Produce a combined snapshot of frontmost app, active browser tab, and text clipboard.

Permission model:

- Read-mostly; it does not send, post, edit, move, or delete anything.
- Selection capture temporarily overwrites a text-only clipboard and refuses to
  run when the clipboard contains non-text formats.
- Screenshot mode writes an explicit PNG file.
- macOS may require Accessibility, Automation, or Screen Recording permission,
  depending on the mode.

### `context-check`

Purpose: fact-check selected/provided text and return concise, sourced context.

What it can do:

- Use provided text, selected text, or the active browser tab as the claim/context.
- Classify the request as a factual claim, entity lookup, source check, or writing support.
- Search current/authoritative web sources when verification or citation is needed.
- Use private connectors only when the source is whitelisted for the request or
  by ignored local config/state.
- Return a verdict, confidence, concise answer, sources, and safer wording when useful.

Permission model:

- Read-only research and writing support by default.
- Uses `mac-context` for selected text or current-tab context when the user asks.
- Defaults to `web` as the only evidence source.
- Connector evidence sources such as Slack, Google Drive, Gmail, Apple Mail,
  and Apple Calendar must be explicitly whitelisted and already authenticated.
- Does not modify drafts, send messages, post, file tickets, or write documents
  unless the user explicitly asks for a separate action.
- Treats selected text, clipboard text, URLs, and screenshots as private.

### `daily-inbox-view`

Purpose: inspect Apple Mail accounts and produce a daily inbox triage preview.

What it can do:

- Discover Apple Mail accounts and mailboxes configured for the current macOS user.
- Print inbox counts or a Markdown table of messages for a local calendar date.
- Include account, Mail message id, received time, sender, subject, and a heuristic recommended action.
- Generate reviewable AppleScript for exact-message actions: open reply drafts, archive, delete, or move to a later/snoozed mailbox.
- Open matching sent-mail messages by exact Apple Mail message id.

Permission model:

- Uses Apple Mail's local AppleScript interface.
- Requires the local macOS user to have Mail configured and to grant automation access if macOS prompts.
- Does not store Mail credentials.
- Defaults to read-only preview behavior.
- State-changing actions require an explicit user request and are generated as inspectable AppleScript before execution.
- Reply actions open draft compose windows only; the skill must not send mail.

### `daily-calendar-view`

Purpose: produce a read-only daily agenda from available calendar sources.

What it can do:

- Query connected Google Calendar and Outlook Calendar sources when those connectors are authenticated in Codex.
- Optionally use local macOS Calendar as a tightly scoped fallback.
- Merge same-day events into a Markdown agenda.
- Surface conflicts, free windows, locations or meeting links, response status, attendee/organizer context, and prep cues when available.

Permission model:

- Uses the calendar connectors already authenticated in the active Codex environment.
- Does not store calendar credentials.
- Must discover source account labels at runtime from connector profile/calendar-listing tools.
- Defaults to read-only behavior.
- Must not create, update, delete, cancel, or respond to calendar events unless the user explicitly requests the exact action and target event.

## Runtime Assumptions

These skills assume an agent/runtime with:

- Access to read skill files from the local filesystem.
- Permission to run local shell scripts bundled with a skill.
- On macOS, permission to use AppleScript/System Events for local context.
- On macOS, optional Accessibility, Automation, and Screen Recording permissions
  for `mac-context` modes that need them.
- Network/search access for `context-check` when the user asks for sourced or
  current verification.
- On macOS, permission to control Apple Mail through AppleScript for Mail workflows.
- Optional `cua-driver` access for launching apps and verifying windows; message and event selection should still be done with deterministic scripts/connectors.
- Optional Google Calendar and Outlook Calendar connector access for calendar workflows.

The skills should treat source systems as the source of truth. Local state, when added later, should store preferences, run history, recommendations, and action plans, not raw credentials or unnecessary private content.

## Codex And `cua-driver`

These skills were created for a Codex setup with `cua-driver` available as a local computer-use MCP server:

```bash
codex mcp add cua-driver -- cua-driver mcp
```

`cua-driver` is useful for launching apps and verifying visible UI state. It is not the primary source of truth for message or event selection. Prefer deterministic interfaces first:

- Apple Mail workflows should use Mail's AppleScript API for account, mailbox, date, and message-id selection.
- Calendar workflows should use authenticated Google/Outlook Calendar connectors when available.
- Local context workflows should use `mac-context` before reaching for broader UI automation.
- Fact-checking and writing-context workflows should use `context-check` over
  selected text, provided text, or the active tab.
- UI automation should be reserved for app launch, visual confirmation, or future workflows where no structured interface exists.

## Install Locally

Symlink a skill into Codex's global skills directory:

```bash
ln -s "$PWD/mac-context" "$HOME/.codex/skills/mac-context"
ln -s "$PWD/context-check" "$HOME/.codex/skills/context-check"
ln -s "$PWD/daily-inbox-view" "$HOME/.codex/skills/daily-inbox-view"
ln -s "$PWD/daily-calendar-view" "$HOME/.codex/skills/daily-calendar-view"
```

## Configuration

These skills do not require a committed `.env`.

- Apple Mail accounts are discovered at runtime from the local Mail app.
- Calendar accounts are discovered from the authenticated calendar connectors available to Codex.
- Keep private preferences, local state, credentials, and generated outputs outside git.
- If workflows need personal overrides, use an ignored local file such as
  `config.local.toml` or a state store outside the repo.
- `context-check` may use `config.local.toml` for local source defaults:

```toml
[context_check]
allowed_sources = ["web", "google-drive", "gmail"]
```

Keep personal account names, state databases, credentials, and generated outputs outside this repo.
