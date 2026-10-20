# Product feedback (draft for the submission form)

Required for every tool, API or SDK used: what it was for, what worked well,
what needs work, onboarding (zero to hello world), would we build with it
again. Fill in the bracketed parts after the device test.

## Bee (CLI, Developer Mode, live stream, facts, photos, todos)
- **Used for:** reading her conversations and transcripts (`conversations list/get`), live lines and
  finished conversations (`stream`), what Bee knows about her (`facts list`), today's photos
  (`photos list/get`), and writing back reminders (`todos create --alarm-at`) and family-approved
  facts (`facts create`). All through our open-source Python client, bee-cli-python.
- **Worked well:**
  - The CLI hides auth and certificates, so any language can use Bee with plain subprocess calls.
  - `--json` everywhere.
  - Final and realtime transcriptions are clearly marked.
  - The live stream makes real-time features possible (a promise becomes a reminder within seconds).
  - Todos with alarms make write-back trivial.
  - Bee runs on an older Apple Watch SE, so a parent's existing watch works.
- **Needs work:**
  - No published language list.
  - Event names are missing from `stream --json`, and the Node library drops them too.
  - Data commands have no documented JSON shapes.
  - The Node library covers about half the CLI.
  - Developer Mode needs a paired device (the hackathon FAQ said otherwise).
  - No stated Node minimum.
  - [Add: Nepali transcription quality from the device test.]
- **Onboarding:** [Time from installing the app to the first `bee conversations list`.]
- **Again?** [Yes/No and why.]

## Alexa+ add-ons (MCP, spec 2025-11-25, Streamable HTTP)
- **Used for:** serving the evening practice as MCP tools, with a `say` line in
  the parent's language for a voice surface.
- **Worked well:** Plain MCP, so the same server works from our Echo Show page,
  Claude, and any MCP host. The add-on design guide's "glanceable, far-field"
  rules shaped the evening screen.
- **Needs work:** No way for builders to test inside Alexa+. Guidance on
  non-English add-ons (Nepali voice output) would help.
- **Again?** Yes, if a public simulator ships.

## Together AI (open models)
- **Used for:** line-by-line translation and practice-card extraction with
  JSON-schema structured outputs; a fast model for the live feed.
- [Fill in after real transcripts: which model won `./run.sh compare` on Nepali, and why.]

## AWS (Amazon Bedrock, for the AWS Builder add-on)
- **Used for:** the same call through Claude on Bedrock (`LLM_PROVIDER=bedrock`), if we run it.
- [Fill in: account setup, model access, quotas.]

## Kiro (AWS Builder add-on)
- **Used for:** building the consent-and-control feature (a `/notice` card for visitors, pause, real delete) from a
  spec (`.kiro/specs/consent-and-control/`: requirements → design → 5 tasks), with steering files holding the product
  rules. We ran Kiro CLI 2.32 headless (`kiro-cli chat --no-interactive`), one task per run, with only the read, glob,
  grep and write tools trusted (no shell); we ran the tests and reviewed the diff after each task. Kiro's output for
  every task is in `.kiro/logs/`. The feature added 28 tests (44 → 72), all passing.
- **What worked:** onboarding took minutes (installer script, Builder ID device login). Kiro read the steering and
  spec files and stayed inside the task. It wrote code in the existing style, found the right touch points itself
  (e.g. that the MCP tools already go through `lane.day()`, so delete needed no MCP change), and wrote solid tests.
  Resuming a cut-off session with `--resume` kept its context.
- **What needs work:** on the free plan the service throttled us in 3 of 7 runs, mid-task. Once it stopped in the
  middle of a file edit and left a SyntaxError (two lines joined). Resuming fixed it, but a throttle should never leave
  a half-applied edit. The IDE hook format (`.kiro/hooks/*.json`) doesn't run in the CLI, so "tests on save" needed a
  human in headless mode.
- **Would we use it again:** yes, for spec-first features with clear tasks. We'd want the throttle to pause and retry
  instead of failing the run.

## Claude Code (coding assistant)
- **Used for:** help with code, debugging and drafting docs. The idea, the product decisions and the testing with my
  mom on her watch are mine.

## bee-cli-python (Open Source add-on)
- A separate MIT repo: a Python client for the Bee CLI. It covers every data command (the bundled
  Node library covers about half), typed live events, reconnects, and `FakeBee` for testing
  without a device. Memory Lane uses it.

