# Devpost submission (draft)

Paste each section into the matching Devpost field. Lines in [brackets] get filled in after the
device test. Keep every claim true: if something wasn't shown on real data, don't say it was.

---

## Name
सम्झना · Memory Lane

## Tagline (one line)
Her day, given back to her, in her own language: evening memory practice built from what her Bee heard.

## Tracks and add-ons
- **Tracks:** Bee (primary), Alexa+
- **Add-ons:** AWS Builder (Kiro), Open Source (bee-cli-python)

---

## Inspiration
About 5.6 million Americans over 65 don't speak English very well (U.S. Census Bureau, American
Community Survey 2024, table B16004). My mom is around sixty, and she doesn't either: she speaks only
Nepali. Lately the details of her day slip away: who called from Kathmandu, what the doctor said
about the new tablet, what she promised her sister.

The apps around her don't speak her language. When she's on a call, I can't always follow it
either, so I can't help her remember. Bee was the first device that could hear her day. We wanted
to give that day back to her, in Nepali.

## What it does
Memory Lane turns the conversations her Bee captures into three things.

**1. She remembers her day.** Every evening, on an Echo Show style screen, she answers five
short questions about her real conversations, in Nepali, in the order they happened:
"आज बिहान काठमाडौंबाट कसले फोन गर्नुभयो?" ("Who called you from Kathmandu this morning?").
- The screen reads each question aloud, in a family member's recorded voice if one exists.
- If she's stuck, she gets a hint. Then she sees the answer with the exact words that were said
  to her, and who said them.
- Photos she took during a conversation become "Who were you with when you took this photo?"
- Questions she misses come back tomorrow; ones she knows come back after 2, 4, 7, then 14 days.

**2. She keeps her word.** When she promises something out loud ("हुन्छ दिदी, म आइतबार फोन
गर्छु" / "Okay sister, I'll call on Sunday"), Memory Lane hears it on Bee's live stream and puts
a reminder with an alarm into her Bee within seconds, while she's still on the call. The family
can undo it.

**3. Her family has her back.** The family page shows every line she hears in Nepali, with its
English appearing a moment later, live.
- Questions about medicine wait until a family member checks them against the doctor's exact words.
- Facts worth keeping ("Kamala is my older sister; she lives in Kathmandu") are suggested, and
  saved to Bee's memory only when the family approves.
- Any conversation can be kept private.

It's memory practice built from her own life. It isn't a treatment, and it never gives medical advice.

## How we built it
- **Bee, at runtime:** the official `bee` CLI, through **bee-cli-python**, an open-source Python
  client we wrote.
  - `bee stream` gives live lines (English under each line, plus real-time promise detection), and
    a finished conversation triggers a sync.
  - `conversations get` gives full transcripts, `facts list` names the people in them, and
    `photos list/get` provides photo questions.
  - `todos create --alarm-at` and `facts create` write back to Bee.
- **Understanding:** open models on Together AI, held to strict JSON schemas.
  - For each conversation, two calls run in parallel: one names speakers, writes a summary and up
    to 3 questions, promises and lasting facts; the other translates every line.
  - Every question cites the transcript lines it comes from. Nothing is thrown away automatically: a question
    the transcript can't back waits for the family to keep or remove it.
  - A fast model reads the last few live lines after each pause to catch promises.
  - We picked the model with a side-by-side tool (`./run.sh compare`) that runs five models on her
    real conversation, read by a Nepali speaker. Kimi K3 (`moonshotai/Kimi-K3`) rebuilt her Nepali best on a real Sunday
    conversation, so it writes the questions and translations; DeepSeek V4 Pro reads the live lines.
- **Practice:** a nightly plan (missed questions first, then today's most important, with one
  photo, in the order the day happened) and Leitner-style spacing, in SQLite.
- **Alexa+:** the same backend is an MCP server (Streamable HTTP, protocol 2025-11-25) with eight
  tools. Each one returns a `say` line in her language for a voice surface. Our Echo Show style
  evening screen is itself an MCP client, so it runs the same practice any Alexa+ device or MCP
  host could. Press M to watch the calls.
- **Kiro:** Kiro built the consent-and-control feature (a notice for visitors, pause, a real delete) spec-first:
  requirements → design → 5 tasks in `.kiro/specs/`, with steering files holding the product rules (evidence only,
  no health advice, respectful Nepali). We ran Kiro CLI headless, one task per run, file tools only, and reviewed and
  tested each task. It added 28 tests; Kiro's output for every task is in `.kiro/logs/`.
- Python, FastAPI, SQLite, plain HTML/JS with no build step, 72 + 42 offline tests (app + library),
  and a sample day so the whole thing runs without a device.

## Challenges we ran into
- **Bee has no Nepali.** Nobody publishes which languages Bee transcribes, so we tested on her watch
  first (`check-bee.sh` measures how much of a transcript is Devanagari). With English selected,
  her Nepali came out as English-sounding nonsense. With Hindi selected, it comes out in Devanagari
  with Hindi spellings and Hindi words swapped in. So Bee runs in Hindi, and the AI is told it's
  reading Nepali heard by a Hindi recognizer: it rebuilds each line as the Nepali most likely said,
  marks the Hindi TV as background, and a question resting only on TV lines is never asked until the family OKs it. The family page shows
  Bee's own words under every rebuilt line, so anyone can check it.
- **Bee keeps only part of her speech.** On her first full day (watch on her wrist), Bee kept 3–12%
  of each conversation as transcript, while English and the Hindi TV came through far better. So
  every question is built only from lines that survived clearly, and garbled lines are marked
  "(unclear)" and never used. It's in our friction log with the measurements.
- **A language none of us could check quickly at scale.** Every question cites its source lines,
  and the family page puts each Nepali line beside its English, so a family member can verify
  anything in seconds.
- **Live events without names.** `bee stream --json` (and the bundled Node library) drop the event
  type, so our client infers it from the payload. That became part of the open-source library.
- **Undocumented data shapes** for photos and facts. We parsed defensively and confirmed on the
  device.
- **Fitting an older adult's eyes and an Echo Show screen:** large type, light theme, one decision
  per screen, every screen fits 1280×800 without scrolling.

## Accomplishments that we're proud of
- My mom wore Bee through three days of Dashain: 25 real conversations, from the Mahanavami puja to tika night,
  became Nepali questions with English for the family. (She hasn't done an evening session yet; the video's
  practice run is labelled as a demo.)
- A promise becomes a reminder in her Bee with one tap from the family page (shown in the video, a real Bee
  todo). The live path, from Bee's stream while she's still talking, is built and tested on a simulated stream;
  it hasn't caught a real promise of hers yet.
- Every question can be traced to the exact words it came from.
- A real open-source contribution: a Python client for every Bee CLI command, with typed live
  events, reconnects and a fake Bee for tests.

## What we learned
- Bee hears Nepali as Hindi, so the raw transcript is often garbled. Rebuilding each line, and keeping "Bee heard"
  on screen beside it, makes mistakes visible instead of hidden.
- Nothing should be dropped silently: uncertain or sensitive questions wait for the family to keep or remove.
- Older adults need fewer, better questions, not more: five a night, in the order of her week.
- Trust comes from showing the source: the quote does more than the answer.

## What's next for Memory Lane
- Answering out loud: she speaks the answer, Bee hears it, and the screen checks it gently.
- Other languages: anything Bee transcribes (the app is language-agnostic; Nepali is the first).
- A weekly note for the family: what she remembered, what keeps slipping.
- Running inside Alexa+ when add-on access opens to builders.

## Built with
bee, bee-cli, bee-cli-python, python, fastapi, sqlite, together-ai, mcp, alexa-plus, kiro, html, javascript

---

## Open Source add-on fields
- **Contribution URL:** https://github.com/woooj02/bee-cli-python
- **Repo URL:** https://github.com/woooj02/bee-cli-python
- **GitHub username:** woooj02
- **Description:** bee-cli-python is a Python client for Bee (bee.computer) through the official
  `bee` CLI. It covers every data command; the Node library bundled with @beeai/cli 0.8.0 covers
  about half (no insights, locations, photos, todo suggestions, transcript polling or searches).
  It also offers:
  - typed live events that keep the event name the Node library drops, or infer it from the payload;
  - automatic reconnects with backoff;
  - helpers for transcripts and Bee's mixed timestamp formats;
  - `FakeBee`, so apps can be tested without a device;
  - `python -m beecli doctor`.

  MIT, 42 tests, Python 3.10+.

## Links
- Demo video: https://www.youtube.com/watch?v=0nj9_PJXPXk
- Code: https://github.com/woooj02/memory-lane
- Live demo (a made-up sample day, so no family data; English mode available): https://memory-lane.91.99.162.43.sslip.io
- Alexa+ MCP endpoint (Streamable HTTP): https://memory-lane.91.99.162.43.sslip.io/mcp
