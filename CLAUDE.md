# LinkedIn Posts Automation — Project Context

## What This Project Is

Automated pipeline that monitors newsletters via Gmail, transforms them into LinkedIn posts using GPT-4o-mini (mimicking Vaibhav Sisinty's writing style), logs output to Google Sheets, and notifies via Telegram.

This is a Python rewrite of the original n8n workflow: `Newsletter to LinkedIn Post - Vaibhav Style (1).json`

---

## RC Engine MCP Server

The RC Engine is registered as an MCP server in Claude Code and should be used to improve brainstorms, plans, and architecture decisions before implementation.

- **Source:** `/Users/hareenedla/Hareen/RC-framework/rc-engine-product-framework/`
- **Entry point:** `dist/index.js` (compiled from `src/index.ts`)
- **Registered via:** `claude mcp add rc-engine node dist/index.js`
- **Config location:** `~/.claude.json` (project: `/Users/hareenedla/Hareen/linkedin-posts`)
- **Rebuild command:** `cd /Users/hareenedla/Hareen/RC-framework/rc-engine-product-framework && npm run build`
- **Activate:** Restart Claude Code after any rebuild

### RC Engine Tools (32 total)
- `prc_*` — Pre-RC research (7 tools)
- `rc_*` — RC phases (14 tools: architect, sequence, validate, forge task, etc.)
- `ux_*` — UX scoring and audit (3 tools)
- `postrc_*` — Post-RC validation (7 tools: security, legal, monitoring)
- `trace_*` — Traceability (3 tools)
- `rc_pipeline_status` — High-level pipeline overview

---

## Original n8n Workflow (Reference)

File: `Newsletter to LinkedIn Post - Vaibhav Style (1).json`

### Flow
```
Gmail Trigger (every minute, from beehiiv + therundown)
  → GPT-4o-mini: Transform newsletter → LinkedIn post (Vaibhav style)
  → GPT-4o-mini: Analyze post → decide image count + write DALL-E prompts
  → JavaScript: Parse image analysis JSON
  → If imageCount > 0:
      → Split images array
      → Gemini 3 Pro: Generate each image
      → Google Drive: Upload image (folder: linkedin_post_pics)
      → Google Sheets: Append row (Date, Newsletter subject, LinkedIn post, Image URL)
  → If imageCount == 0:
      → BUG: no connection to Google Sheets (posts without images are never saved)
```

### Known Bugs in Original
- False branch of the `If` node (no images) has no connection — posts with 0 images are never logged to Google Sheets
- HTTP Request node (xAI Grok image API) is completely disconnected — leftover test node

### Newsletter Sources
- `stayingahead@mail.beehiiv.com`
- `news@daily.therundown.ai`

### Google Sheet
- ID: `1FWz4l7mrtSQQTVEbRAqh-sguDNmaEvuYmr9tWUbsgrg`
- Sheet: `Sheet1`
- Columns: `Date`, `News_Letter_subject`, `LinkedIn Post`, `Post_Pics_URL`

---

## Python Rewrite — Brainstorm Decisions

### Confirmed Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Gmail monitoring | Gmail API + Push Notifications (Pub/Sub) | Real-time, no polling loop |
| Web server | Flask | Lightweight webhook receiver |
| LLM | GPT-4o-mini | Already in use, cost-effective |
| Image generation | Skipped for now | Focus on core flow first, add later |
| Telegram notification | Full post content | Review post without opening browser |
| Project structure | Multi-file Python modules | Clean separation of concerns |

### Planned File Structure
```
newsletter-to-linkedin/
├── main.py                  # Flask app + /webhook endpoint
├── gmail_client.py          # Gmail API — fetch full email body
├── content_generator.py     # GPT-4o-mini — generate LinkedIn post (Vaibhav style)
├── sheets_logger.py         # Append row to Google Sheets
├── telegram_notifier.py     # Send full post to Telegram bot
├── config.py                # All env vars in one place
├── requirements.txt
└── .env.example
```

### Pipeline Flow (Python)
```
Gmail Push (Pub/Sub webhook)
  → Flask /webhook
      → Verify push notification authenticity
      → Fetch full email via Gmail API
      → Filter: only process from allowed senders
      → GPT-4o-mini generates LinkedIn post
      → Append row to Google Sheets
      → Send full post to Telegram bot
```

### Prerequisites (All Ready)
- Google Cloud project (Gmail API + Sheets API + Drive API enabled)
- OpenAI API key
- Telegram bot token + chat ID
- Google Sheet (`linkedin_posts`) already exists

---

## Vaibhav Sisinty Writing Style Rules (for GPT Prompt)

The LinkedIn post must follow this exact structure and tone:

1. **Hook** — Bold, provocative, emoji-led first line (e.g. "AI just turned learning upside down.")
2. **Amplifier** — "And I'm not making this up" + downward arrow emoji
3. **White space** — Max 2-3 lines per paragraph, single-line emphasis statements
4. **Pacing device** — Every 150-200 words: "Let that sink in." or "Think about that."
5. **Specific numbers** — Exact data, product names, percentages from the newsletter
6. **Before/after contrast** — Show transformation clearly
7. **Narrative arc** — Hook → Context → Examples → Twist → Insight → Question
8. **Reader addressing** — "Here's what this means for you:", "But here's the twist:"
9. **Emoji strategy** — 5-8 emojis total, used structurally not decoratively
10. **Philosophical CTA** — End with a debate-worthy question (never yes/no)
11. **Hashtags** — 8-12 relevant hashtags at the end

### Formatting Rules (CRITICAL)
- ZERO asterisks (* or **)
- ZERO dashes for lists (-)
- ZERO hashtags (#) for headers
- ZERO promotional content (no "AI Survival Hackbook", no CTAs, no download links)
- Plain text + emojis only
- 400-600 words
- 100% copy-paste ready for LinkedIn

---

## Environment Variables Needed

```env
# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=

# Gmail Push (Pub/Sub)
GMAIL_PUBSUB_TOPIC=
GMAIL_WATCH_LABEL=INBOX

# OpenAI
OPENAI_API_KEY=

# Google Sheets
GOOGLE_SHEET_ID=1FWz4l7mrtSQQTVEbRAqh-sguDNmaEvuYmr9tWUbsgrg

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Allowed newsletter senders
ALLOWED_SENDERS=stayingahead@mail.beehiiv.com,news@daily.therundown.ai

# Flask
PORT=8080
```

---

## Status

- [x] Original n8n workflow analyzed
- [x] RC Engine MCP server built and registered
- [x] Brainstorm completed — architecture decisions locked
- [x] RC Engine ALL 8 phases complete (Illuminate → Define → Architect → Sequence → Validate → Forge → Connect → Compound)
- [x] Post-RC security scan complete — APPROVED, READY TO SHIP
- [x] Python project scaffolded (src/ structure, requirements.txt, .env.template, .gitignore)
- [x] Gmail API + Pub/Sub webhook + /health endpoint (src/api/webhook.py)
- [x] Gmail client with sender allowlist + retry (src/integrations/gmail_client.py)
- [x] GPT-4o-mini content generation implemented (src/services/content_transformer.py)
- [x] Google Sheets logging + read_range() + retry (src/integrations/sheets_client.py)
- [x] Telegram notification implemented (src/integrations/telegram_client.py)
- [x] Deduplication service (src/services/deduplication.py)
- [x] Pipeline orchestrator with fallback logging (src/services/pipeline.py)
- [x] Structured JSON logging + retry with exponential backoff (src/utils/)
- [ ] .env filled with real credentials
- [ ] Gmail Pub/Sub watch set up (one-time Google Cloud setup)
- [ ] End-to-end tested with real newsletters
- [ ] Image generation added (future)

## Next Steps (deploy)

1. Fill `.env` with real credentials (see Environment Variables section)
2. Set up Gmail Pub/Sub watch (one-time):
   ```bash
   # Call Gmail API to watch inbox
   POST https://gmail.googleapis.com/gmail/v1/users/me/watch
   { "topicName": "projects/{project}/topics/{topic}", "labelIds": ["INBOX"] }
   ```
3. Create "Processed IDs" sheet tab in the Google Sheet with headers: `Message ID | Processed At | Status`
4. Deploy Flask app: `python src/main.py`
5. Expose `/webhook/gmail` via ngrok or Cloud Run
6. Verify `/webhook/health` returns 200

## RC Engine State

- RC Method project: `Newsletter to LinkedIn Post Automation`
- All 8 phases complete, post-RC gate approved
- SQLite state: `/Users/hareenedla/Hareen/linkedin-posts/.rc-engine/state.db`
- Known issue: artifact registration bug in RC Engine — state.artifacts must be manually patched in SQLite if resuming mid-session (see previous session notes)

## Generated File Structure

```
src/
├── main.py                        # Flask app entry point
├── api/
│   └── webhook.py                 # Gmail Pub/Sub /webhook endpoint
├── config/
│   └── logging_config.py          # JSON logging setup
├── integrations/
│   ├── gmail_client.py            # Gmail API + sender validation
│   ├── sheets_client.py           # Google Sheets append
│   └── telegram_client.py        # Telegram bot notifications
├── services/
│   ├── content_transformer.py     # GPT-4o-mini (Vaibhav style)
│   ├── deduplication.py           # Processed ID tracking
│   └── pipeline.py                # Main orchestrator (INCOMPLETE)
└── utils/
    ├── logger.py                  # Structured JSON logger
    └── retry.py                   # Exponential backoff decorator
tests/                             # Pytest test suite
requirements.txt
.env.template
.gitignore
```
