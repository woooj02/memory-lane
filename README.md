# सम्झना · Memory Lane

**Her day, given back to her, in her own language.**

About 5.6 million Americans over 65 don't speak English very well (U.S. Census Bureau, ACS 2024,
table B16004). My mom is one of them. She's in her sixties, speaks only Nepali, and the details of
her day are getting harder to hold on to: who called, what the doctor said, what she promised.
The apps around her don't speak her language, and neither do I, fast enough to follow every
conversation.

Memory Lane does three things with the day her Bee hears:

1. **She remembers her day.** Each evening, a few short questions about her real conversations,
   in Nepali, in the order the day happened: "आज बिहान काठमाडौंबाट कसले फोन गर्नुभयो?"
   ("Who called you from Kathmandu this morning?"). A hint if she's stuck, then the answer with the
   exact words that were said. Questions she misses come back tomorrow; ones she knows come back
   after 2, 4, 7, then 14 days. Photos from her day become "Who were you with?".
2. **She keeps her word.** When she promises something out loud ("I'll call you on Sunday"), it
   lands in her Bee as a reminder with an alarm while she's still talking.
3. **Her family has her back.** Every line she hears appears in Nepali beside its English, live.
   Questions about medicine are only asked after a family member checks them against what the
   doctor said. The family can record a question in their own voice for her to hear.

It's memory *practice*, built from her own life. It isn't a treatment and gives no medical advice.

Built for the Bee track of [Build, Ship, Shape](https://amazonappdev2026.devpost.com/), with the
same backend served as an Alexa+ add-on (an MCP server) for the Alexa+ track.

## How it works

```
Apple Watch / Bee ─► Bee cloud ─► bee CLI ─► bee-cli-python ─► Memory Lane (FastAPI)

  live     bee stream ──────► each line ─► English (fast model) ─► family page, live
                                        └► promise? ─► bee todos create --alarm-at   (seconds)
  digest   bee conversations get ─┐
           bee facts list ────────┼─► AI, in parallel: speakers, summary, suggested questions,
                                  │   promises, lasting facts · every line translated
           bee photos list ───────┴─► "who were you with?" from who was talking then
           ─► SQLite: questions, spaced review, promises, facts
  back     bee todos create (promises) · bee facts create (family-approved facts)

  /          evening screen, Echo Show 1280×800, itself an MCP client
  /family    family page          /how   the pipeline with live counts
  /mcp       MCP server, Streamable HTTP, protocol 2025-11-25
```

- **Bee, at runtime** (`app/bee.py`), through
  [bee-cli-python](https://github.com/woooj02/bee-cli-python), our open-source Python client for
  the official `bee` CLI:
  - The live stream feeds the family page and real-time reminders. A finished conversation
    triggers a sync, and a sync also runs every 10 minutes as a safety net.
  - Bee's facts help name the people in her conversations.
  - Her photos become photo questions.
  - Promises and family-approved facts are written back to Bee.
- **AI** (`app/digest.py`, `app/llm.py`): open models on Together AI by default
  (`TOGETHER_MODEL` for questions and translation, `TOGETHER_FAST_MODEL` for live lines), or
  Claude on the API or Amazon Bedrock.
  - Every answer is held to a JSON schema.
  - Questions cite the transcript lines they come from. One that can't (no line, or only TV lines) isn't dropped:
    it waits on /family for the family to keep or remove, like health questions.
  - `./run.sh compare` runs several models on one conversation and writes a side-by-side, so the
    model is chosen by someone who reads Nepali.
- **Practice** (`app/service.py`): six questions a night.
  - Up to two missed questions from earlier days come first, then today's most important ones
    (always one photo if there is one), in the order they happened.
  - Questions are read aloud, in a family member's recorded voice when there is one. Otherwise
    the device's Nepali voice is used, falling back to Hindi, which uses the same script.
- **Alexa+** (`app/mcp_server.py`): eight tools: `start_evening_practice`, `get_hint`,
  `reveal_answer`, `record_recall`, `todays_conversations`, `list_promises`, `remind_me`,
  `recall_progress`. Each one returns a `say` line in the parent's language for a voice surface.

## Run it

```bash
./run.sh setup            # once: venv + dependencies (installs ../bee-cli-python too)
cp .env.example .env      # add TOGETHER_API_KEY
./run.sh                  # http://127.0.0.1:8110   family: /family   how: /how
./run.sh test             # 72 offline tests
./run.sh compare          # which Together model reads Nepali best (needs the key)
./run.sh manual           # no AI calls: export transcripts, digest them by hand, apply (LLM_PROVIDER=manual)
```

With no `bee` CLI on the PATH, the app runs on a sample day (`fixtures/demo_day.json`: five
conversations in Nepali, two photos, two known facts). With no AI key, it uses hand-written
sample translations for that day. Both are labelled on the family page. On the sample day,
**Play the morning call live** on /family streams a call and fires a real-time reminder.

### With the real Bee

```bash
nvm use 20                          # the bee CLI needs Node 18+
npm install -g @beeai/cli
bee login                           # approve in the Bee app (Developer Mode on)
./check-bee.sh                      # go/no-go: login, recordings, Nepali script
./run.sh                            # BEE_MODE=auto picks the CLI
```

The first device test is described step by step in `SATURDAY.md`.

**Nepali on Bee.** Bee has no Nepali recognizer. Set the Bee app to **Hindi** (English as second language): it writes
her Nepali in Devanagari with Hindi spellings. `BEE_HEARS=Hindi` (the default when `PARENT_LANG=ne`) tells the AI so,
and it rebuilds each line as the Nepali most likely said and marks TV/background lines. The family page shows the
rebuilt line with Bee's own words under it.

### Evening screen keys (for recording)

| Key | Action |
|---|---|
| `1` | I remember |
| `2` | Hint |
| `3` | I forgot |
| `N` / `Enter` | Next |
| `R` | Read aloud |
| `V` | Auto read-aloud on/off |
| `L` | Language: नेपाली → नेपाली + English → English |
| `M` | MCP calls |

`/?lang=both` opens it in Nepali + English, and `/?mcp=1` starts with the MCP panel open.
**Reset tonight's practice** on /family undoes the evening so it can be recorded again.

## Privacy and consent

The recordings include other people, so:
- **Notice for visitors.** `/notice` is a one-screen card in Nepali and English she can show
  anyone: "Bee is listening to help me remember my day — only my family sees it — just say so and
  I'll stop." The family page links to it.
- **Pause.** The family page offers "Pause for 1 hour", "Pause until tomorrow" and "Resume". While
  paused the live feed stops, real-time reminders don't fire, and any conversation that started
  during the pause is stored without its transcript so no questions are ever made from it.
- **Delete for real.** Each conversation on the family page has a "Delete" button with an inline
  confirmation. Deleting removes the transcript, translation, cards, reviews, promises, facts and
  photos in one go and leaves only a tombstone so a re-sync doesn't bring it back. The confirmation
  notes that Bee keeps its own copy and how to remove it in the Bee app.
- **Keep private:** any conversation can be marked private. No questions are made from it and
  nothing about it is shown.
- **Health:** medicine questions wait for a family member's approval and only quote what was said.
- **On a server, real transcripts never go out without `ACCESS_TOKEN`** in `.env`; it guards
  every page, API call, photo, recording and `/mcp`. Open `https://…/?token=<token>` once and it
  becomes a cookie; MCP clients send `Authorization: Bearer <token>`.

## Deploy

`./deploy.sh` ships to the Hetzner box (tests run first). The box has no `bee` CLI, so it serves
the **sample day**, a safe public demo for judges.

## Settings (`.env`)

| Var | Default | |
|-----|---------|-|
| `TOGETHER_API_KEY` | – | Together AI, the default engine. Without any AI key the AI step uses the samples |
| `TOGETHER_MODEL` / `TOGETHER_FAST_MODEL` | `moonshotai/Kimi-K3` / `deepseek-ai/DeepSeek-V4-Pro-0813` | Questions and translation / live lines. Pick with `./run.sh compare` |
| `ANTHROPIC_API_KEY` | – | Claude API, used when there's no Together key |
| `LLM_PROVIDER` | auto | `together`, `anthropic`, `bedrock`, `mock`, or `manual` (no AI calls; digest by hand with `./run.sh manual`) |
| `BEE_HEARS` | `Hindi` for Nepali | The language Bee's recognizer is set to, when it isn't the parent's |
| `CLAUDE_MODEL` / `CLAUDE_EFFORT` | `claude-opus-5-5` / `medium` | |
| `AWS_REGION` / `BEDROCK_MODEL` | `us-west-2` / `anthropic.claude-opus-5-5` | For `LLM_PROVIDER=bedrock` |
| `BEE_MODE` | `auto` | `cli` (real Bee) or `demo` (sample day) |
| `PARENT_NAME` / `PARENT_LANG` / `PARENT_LANG_NAME` | `आमा` / `ne` / `Nepali` | Who practises, and in which language |
| `TZ_NAME` | `America/Denver` | Their day boundary |
| `SESSION_SIZE` | `6` | Questions per evening |
| `MIN_WORDS` | `25` | Shorter conversations are skipped |
| `PHOTO_CARDS` | `2` | Photo questions per day (0 turns them off) |
| `LIVE_REMINDERS` | `1` | A promise said out loud becomes a Bee reminder within seconds |
| `LIVE_TRANSLATE` | `1` | English under each live line |
| `SYNC_MINUTES` | `10` | Safety-net sync interval with the real Bee |
| `ACCESS_TOKEN` | – | Required for every page, API, media file and `/mcp` when set |
| `MCP_ALLOWED_HOSTS` | – | Extra host names for `/mcp` (deploy sets its own) |

## Files

| Path | What |
|------|------|
| `app/bee.py` | Bee sources (real, via bee-cli-python; and the sample day) |
| `app/digest.py` | Prompts and JSON schemas: understand, translate, live promises, photo questions |
| `app/llm.py` | Together AI / Claude API / Amazon Bedrock client |
| `app/service.py` | Sync, practice plan, spacing, approvals, promises, facts, voice, live reminders |
| `app/compare.py` | `./run.sh compare`: models side by side on one conversation |
| `app/mcp_server.py` | The Alexa+ add-on (MCP tools) |
| `app/main.py` | HTTP routes, access token, SSE live feed, media, `/mcp` mount |
| `web/index.html` | Evening screen (MCP client) |
| `web/family.html` · `web/how.html` | Family page · how-it-works page |
| `.kiro/` · `KIRO.md` | Kiro steering, hook and spec (AWS Builder add-on) |
| `check-bee.sh` · `SATURDAY.md` | Bee go/no-go checks · the first device test |
| `VIDEO.md` · `DEVPOST.md` | The demo video plan · the submission text |
| `FRICTION_LOG.md` · `PRODUCT_FEEDBACK.md` | For the submission |

## License

MIT
