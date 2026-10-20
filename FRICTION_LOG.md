# Friction log

Submissions with friction logs earn up to a 10% judging bonus. One entry per
problem, written when it happens. Format from the official rules: task, steps,
expected vs actual, severity, workaround, suggestion.

Severity: **High** blocks progress · **Medium** costs real time · **Low** annoyance.

---

## 1. Hackathon FAQ said Bee Developer Mode works without a device
- **Task:** Find out whether the Bee track can be built before we have hardware.
- **Steps:** Read the hackathon FAQ (said Developer Mode does not need a device), then the forum.
- **Expected:** One consistent answer.
- **Actual:** An organizer replied on the forum (Oct 11) that the FAQ line is wrong: Developer Mode only appears after pairing a Bee or an Apple Watch.
- **Severity:** High (decides whether the track is possible at all).
- **Workaround:** Borrowed an Apple Watch running Bee.
- **Suggestion:** Fix the FAQ line, and say on docs.bee.computer that Developer Mode requires a paired device.

## 2. No published list of the languages Bee transcribes
- **Task:** Check whether Bee can transcribe Nepali before building for a Nepali-speaking parent.
- **Steps:** Searched bee.computer, the product pages, docs.bee.computer, the bee-cli source and README.
- **Expected:** A list of the "40+ languages".
- **Actual:** Only "supports up to 40 languages" (and "40+" elsewhere on the same page). No list, no per-language quality notes.
- **Severity:** Medium (we had to plan a fallback without knowing).
- **Workaround:** A go/no-go test on the device (`check-bee.sh` measures how much of the transcript is Devanagari).
- **Suggestion:** Publish the language list, and expose the detected language per conversation in the API.

## 3. `bee stream --json` drops the event name
- **Task:** React when a conversation ends, to build that evening's questions right away.
- **Steps:** `bee stream --json --types new-utterance,update-conversation`.
- **Expected:** Each JSON line says which event it is.
- **Actual:** `--json` prints only the event's `data`; the event name (`new-utterance`, `update-conversation`) is lost. We infer it from the payload's keys.
- **Severity:** Low.
- **Workaround:** `classify_event()` in `app/bee.py` reads the shape (`utterance` → new utterance, `conversation.end_time` → ended).
- **Suggestion:** Emit `{"event": ..., "data": ...}` in JSON mode, or add a `--json-envelope` flag.

## 4. bee CLI needs a newer Node than many machines have
- **Task:** Install the CLI.
- **Steps:** `npm install -g @beeai/cli` on a machine with Node 14.
- **Expected:** A clear minimum version up front.
- **Actual:** The README doesn't state a minimum Node version.
- **Severity:** Low.
- **Workaround:** `nvm install 20`.
- **Suggestion:** Add `"engines": {"node": ">=18"}` to package.json and a line in the README.

## 5. No way to reach Alexa+ itself
- **Task:** Show the Memory Lane MCP server running inside Alexa+.
- **Steps:** Read the Alexa+ add-on docs; setup guides mention the MCP Toolkit and web simulator.
- **Expected:** Some sandbox to test an add-on.
- **Actual:** The toolkit, CLI and simulator are partner-only. Some setup pages don't say so.
- **Severity:** Medium.
- **Workaround:** Built our own Echo Show-style page that is a real MCP client over Streamable HTTP.
- **Suggestion:** A public, rate-limited Alexa+ add-on simulator, even text-only, would let builders test the real routing.

## 6. The Node library drops the event name from the live stream
- **Task:** Use `@beeai/cli/lib` (`createJsonSseStream`) to react to different live events.
- **Steps:** Read `dist/lib/index.js` in @beeai/cli 0.8.0.
- **Expected:** Each event arrives with its type (`new-utterance`, `update-conversation`, ...).
- **Actual:** `normalizeJsonPayload` skips `event:` lines, so callers only get `data`. `todo-created` and `todo-updated` carry identical payloads and can't be told apart.
- **Severity:** Medium.
- **Workaround:** Our open-source bee-cli-python keeps `event:` names when present and infers the type from the payload otherwise (`Event.exact` says which).
- **Suggestion:** Yield `{event, data}` from the library, and add the event name to `bee stream --json` lines.

## 7. Data commands have no documented JSON shapes
- **Task:** Turn today's photos and facts into practice questions.
- **Steps:** Read the CLI README for `photos list --json`, `facts list --json`, `locations recent --json`.
- **Expected:** Field names (photo time, fact text, confirmed) like the README gives for stream events.
- **Actual:** Stream events are documented with example payloads; the data commands aren't. The bundled TypeScript types return `unknown`.
- **Severity:** Medium (we had to parse several possible field names until we could see real output).
- **Workaround:** Defensive parsing (`photo_time()` tries 8 field names), then checked on the device.
- **Suggestion:** Example JSON for each data command in the README, and typed return values in `dist/lib`.

## 8. The Node library covers about half the CLI
- **Task:** Use facts search, todo suggestions, insights, locations and photos from code.
- **Steps:** Compare the README's command list with `createDataApi` in `dist/lib`.
- **Expected:** The library mirrors the CLI.
- **Actual:** No insights, locations, photos, `todos complete/suggestions`, `conversations transcript/related`, `daily find`, `facts search` or `journals search`.
- **Severity:** Low for us (we shell out), higher for Node builders.
- **Workaround:** bee-cli-python covers every data command, with tests.
- **Suggestion:** Generate the library from the same command definitions as the CLI.

<!-- Add entries from the device test below. -->

## 9. Bee has no Nepali, and the nearest language mangles it
- **Task:** Transcribe my mom's day; she speaks only Nepali.
- **Steps:** Bee app language settings on the iPhone. Recorded once with English selected, then with Hindi (Oct 18).
- **Expected:** Nepali, or a way to say which language is spoken.
- **Actual:** No Nepali in the list. With English selected, her Nepali came out as English-sounding nonsense. With Hindi selected, it comes out in Devanagari with Hindi spellings and Hindi words swapped in ("मैंले बुच्छा" for "मैले बुझें"), close enough to rebuild.
- **Severity:** High (the whole product depends on it).
- **Workaround:** Bee set to Hindi; a model is told the transcript is Nepali heard by a Hindi recognizer, rebuilds each line as the Nepali most likely said, and marks fluent Hindi (the TV) as background. Bee's own words stay visible next to the rebuilt line so a family member can check. (`BEE_HEARS` in `app/config.py`.)
- **Suggestion:** Add Nepali (Whisper-class models already support it), or an "unlisted language" mode that keeps the raw audio-to-text instead of forcing a listed language.

## 10. Bee keeps only a small part of speech in a language it doesn't fully know
- **Task:** Capture whole conversations from her wrist.
- **Steps:** Apple Watch on her wrist, capture on, Hindi selected, normal family conversations (Oct 18–19). Measured the seconds of speech in each final transcript (utterance `end - start`).
- **Expected:** Most of a conversation she talks through.
- **Actual:** She talked through a 24-minute conversation; the transcript holds 2 min 39 s (11%). Other conversations: 4–6%. In the same recordings the English café order came through word for word, and a Hindi TV serial kept the most (20%). Bee's conversation list and summaries show the same gaps, so it isn't the CLI.
- **Severity:** High (most of her day never reaches the API).
- **Workaround:** Questions are made only from lines that survive; garbled lines are marked "(unclear)" and never used.
- **Suggestion:** Don't drop low-confidence speech silently: keep it as an utterance flagged low-confidence, or report how much audio was discarded per conversation, so developers can tell "she was quiet" from "we couldn't understand her".

## 11. Capture on the Apple Watch has to be started by hand
- **Task:** Record her day without her having to remember anything.
- **Steps:** Bee app on the Apple Watch.
- **Expected:** Capture starts when the watch is worn, or on a schedule.
- **Actual:** It records only after "Touch to start" on the watch. There is no auto-start and nothing to start it from the iPhone or the API, which is hard for an older user who forgets.
- **Severity:** Medium.
- **Workaround:** A daily phone reminder for the family to ask her to start it.
- **Suggestion:** Auto-start on wrist, a schedule, or a remote start from the paired iPhone.

## 12. Together AI: Qwen models refused on our account
- **Task:** Compare models for the Nepali rebuild (`./run.sh compare`).
- **Steps:** Called Qwen/Qwen3.7-Max and Qwen/Qwen3.8-Flash.
- **Expected:** A response, or a clear note in the model list.
- **Actual:** 403 "This model sends your prompts to a third-party provider". The model list doesn't say which models need that opt-in.
- **Severity:** Low.
- **Workaround:** DeepSeek for live lines, Kimi for the full rebuild.
- **Suggestion:** Mark those models in `/v1/models`, and link the setting in the error.

## 13. Kiro CLI: a throttle mid-edit left broken code
- **Task:** Build the consent features with Kiro CLI, one spec task per run (`kiro-cli chat --no-interactive`).
- **Steps:** Free plan (Builder ID), 7 runs over about 25 minutes.
- **Expected:** Each run finishes its task, or stops cleanly between edits.
- **Actual:** "The request was throttled by the service" ended 3 of 7 runs. In one, the file being edited was left
  with two lines joined into one: a SyntaxError that broke the whole test suite.
- **Severity:** Medium.
- **Workaround:** `kiro-cli chat --resume` with a note about the error; Kiro fixed it and finished the task.
- **Suggestion:** Retry with backoff on throttling in headless mode, and apply each edit atomically so a cut-off run
  never leaves a half-written file. Show the remaining quota before a run starts.
