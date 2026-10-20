# Design: consent and control

## Notice (`/notice`)
- New page web/notice.html, same type scale and light theme as the evening screen (Mukta, large).
- Text in both languages, for example:
  - ne: "नमस्ते! मेरो घडीमा Bee ले कुराकानी सुन्छ, ताकि बेलुका मलाई दिनभरिको कुरा सम्झन मद्दत होस्। यो मेरो परिवारले मात्र हेर्छ। तपाईं चाहनुहुन्न भने भन्नुस्, म रोकिदिन्छु।"
  - en: "Hi! Bee on my watch is listening, to help me remember my day in the evening. Only my family sees it. If you'd rather not, just say so and I'll stop it."
- The Nepali wording must be checked by the family before the demo.

## Pause
- `settings` key `pauses`: JSON list of `{start_ms, end_ms}`. Helpers in app/service.py:
  `pause(minutes | until_tomorrow)`, `resume()`, `paused_at(ms) -> bool`, `pause_state()`.
- `status()` gains `paused_until`.
- `Live.line()` is skipped while paused (MemoryLane checks before calling it in `_live_loop` and `replay_demo`).
- `sync()`: when `paused_at(conversation start)`, save as skipped with reason "paused" and empty utterances.
- Routes: `POST /api/pause {"minutes": 60}` or `{"until": "tomorrow"}`, `POST /api/resume`.

## Delete
- `Store.delete_conversation(cid)`: one transaction removing reviews of its cards, cards, promises, facts and
  photo files, then the conversation row's text fields; set `status='deleted'`. (Keep the row as the tombstone.)
- `sync()` skips ids with status `deleted` even with `redo=True`.
- Every query that lists conversations, cards, promises or facts excludes `status='deleted'`.
- Route: `DELETE /api/conversations/{cid}`.
- Family page: "Delete" opens an inline confirm row ("Delete everything Memory Lane has from this conversation?
  Bee keeps its own copy: delete it in the Bee app under Conversations.") with Delete / Cancel.

## Tests (tests/test_app.py)
- Pause: a conversation starting inside a pause is skipped with no text; one after it is digested; resume works.
- Live lines are dropped while paused; reminders aren't set.
- Delete: cards, reviews, promises, facts and photo files are gone; re-sync (with redo) doesn't restore it;
  MCP `todays_conversations` doesn't list it.
- /notice returns 200 and contains both languages.
