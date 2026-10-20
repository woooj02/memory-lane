# Requirements: consent and control

## Introduction
Memory Lane is built on recordings of real conversations, and other people are in them. The family
and the people Mom talks to need simple, visible ways to know about the recording and to keep
things out of it. This spec adds a visitor notice, a pause, and a real delete.

## Requirement 1: a notice Mom can show
**User story:** As Mom, I want a simple card I can show a visitor, so they know Bee is listening and why.

Acceptance criteria:
1. The system SHALL serve `/notice`: one screen with large type, in the parent's language and in English, saying that Bee may record the conversation for her memory practice, that only family sees it, and that she can stop it any time.
2. The notice SHALL fit on a phone screen (390×844) without scrolling, and on the 1280×800 evening screen.
3. The family page SHALL link to it ("Show visitors the notice").

## Requirement 2: pause
**User story:** As a family member, I want to pause Memory Lane for a visit or a private talk, so nothing from that time becomes questions or appears on the family page.

Acceptance criteria:
1. The family page SHALL offer "Pause for 1 hour", "Pause until tomorrow" and "Resume", and show when a pause ends.
2. WHILE paused, the live feed SHALL show "Paused" instead of lines; live English and real-time reminders SHALL stop.
3. WHEN a sync runs, conversations that started during a pause SHALL be stored as `skipped` with the reason "paused", with no transcript text, and no cards, promises or facts.
4. Pauses SHALL be stored (settings table) so they survive a restart, and be visible on /how as a count.

## Requirement 3: delete for real
**User story:** As a family member, I want to delete a conversation completely, so it can't come back.

Acceptance criteria:
1. Each conversation on the family page SHALL have "Delete", with a confirmation step on the page (no browser dialog).
2. WHEN deleted, the system SHALL remove its transcript, translation, cards (and their reviews), promises, facts and photos, and keep only a tombstone (id + deleted time) so a re-sync doesn't bring it back.
3. The confirmation SHALL say that Bee keeps its own copy, and how to delete it in the Bee app.
4. Deleted conversations SHALL never appear in practice, MCP tools, the family page or the live feed.

## Requirement 4: say it plainly
1. The family page header SHALL show "Recording with Bee · tell the people she talks to" with a link to /notice.
2. README SHALL have a short "Privacy and consent" section describing the three controls.
