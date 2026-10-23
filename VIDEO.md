# Demo video plan (under 3:00)

Judges may score from this video alone, and aren't required to watch past 3:00.

**The story in one line:** her day, given back to her, in her own language.
Three promises, and every scene serves one of them:
1. **She remembers her day.** Evening practice built from her real conversations.
2. **She keeps her word.** What she promises out loud lands in Bee as a reminder.
3. **Her family has her back.** Every Nepali line in English, and medicine questions checked first.

The video follows **her real Dashain week** (Sun Oct 18 – Tue Oct 20). It is not a feature tour: if a feature
doesn't move her week forward, it stays out (facts and Alexa+ get a few seconds at the end).

It must also prove, fast:
- **Live Bee data** (Stage 1 is pass/fail on this): the Bee app with today's date, and lines arriving live.
- **A real person and a real need** (Impact, Idea).
- **Non-trivial tech** (Tech, the first tie-breaker): live stream, real-time reminders, grounded questions, MCP.

Record at 1920×1080. Browser zoom 125% on the family page, 100% on the evening screen (sized for
an Echo Show). English narration in your voice, with English captions under all Nepali. No music
with lyrics; no third-party music, footage or logos; no Alexa+ logo ("Simulated Alexa+" text is fine).

## The opening number (sourced)
**"5.6 million Americans over 65 don't speak English very well. My mom doesn't either."**
Source: U.S. Census Bureau, American Community Survey 2024 1-year, table B16004 (age 65+, speak
English less than "very well": 5,565,363 of 61.2 million, about 1 in 11). Put the source in small
text on screen and in the Devpost description. Use no other statistics, and never imply it
treats memory loss: it's practice.

## How judges follow the Nepali
The evening screen has a language switch (top right, or key **L**): नेपाली / नेपाली + English /
English. Use **नेपाली + English** for most of the evening, one short shot in Nepali only, and one
"same screen, now in English" beat. The family page is always English beside Nepali.

## Storyboard (rewritten Oct 23 for her real Dashain week; the word-for-word script is in [SCRIPT.md](SCRIPT.md))

The first plan (sister's call, doctor visit, park photo, a live promise) needed scenes Bee never caught. This
version uses only her real Bee data: 25 conversations over Sun–Tue, with Monday's Mahanavami puja and Tuesday's
nail salon, Dashain shopping and tika night. Every question and translation on screen was made by the open model on
Together AI and checked on the family page.

| Time | Scene | On screen | Promise it serves |
|---|---|---|---|
| 0:00–0:12 | **Her** | Mom, the pink watch. The sourced number. | – |
| 0:12–0:20 | **Consent** | `/notice` card. | – |
| 0:20–0:47 | **Her real Dashain week** | Bee app list, Tue → Sun (proof). `/family?day=2026-10-19`: the priest's Sanskrit at the Mahanavami puja; → Tuesday: a Durga-shopping line rebuilt from "Bee heard" into Nepali + English; TV tagged. | Her family has her back |
| 0:47–1:02 | **Waiting for your OK** | Knee therapy (health) → **Remove**. The café order ("Check": tagged background) → **Keep**. "Nothing is thrown away on its own." | Her family has her back |
| 1:02–1:15 | **She keeps her word** | "Not now. Next time." → **Add to her Bee reminders** → the reminder in the Bee app. | She keeps her word |
| 1:15–2:07 | **Evening** | Evening screen, नेपाली + English. Monday: the purse → the supari at the puja (hint). Tuesday: the twins → eyebrows → the flower → the tika. **L** to English. | She remembers her day |
| 2:07–2:14 | **Score** | "[X] of 6". | She remembers her day |
| 2:14–2:40 | **How it's built** | `/how`, the MCP panel (**M**), the bee-cli-python README, the Kiro spec. | – |
| 2:40–2:52 | **Close** | Mom at the screen. सम्झना · Memory Lane. | – |

## Before recording
- Tonight's 6 questions are pinned (setting `plan:2026-10-23`, and `plan:2026-10-24` in case filming runs
  past midnight). **Reset tonight's practice** now keeps the same questions and only undoes the answers.
- The family page shows any day: `?day=YYYY-MM-DD`, or ← / → beside the heading.
- Keys on the evening screen: **1** remember · **2** hint · **3** forgot · **N/Enter** next · **R** read aloud ·
  **V** auto read-aloud · **L** language · **M** MCP panel.

## Shots to collect
- [ ] iPhone: the Bee app's conversation list, Tue Oct 20 back to Sun Oct 18 (proof)
- [ ] Screen: family page Monday and Tuesday (Beats 3–5), one continuous take each for Beats 4 and 5
- [ ] iPhone: the reminder Beat 5 creates
- [ ] Screen + Mom: the evening practice, 2–3 takes
- [ ] Mom at the table with the watch (open), Mom at the screen (close), with her OK
- [ ] `/how`, the MCP panel, the README, the Kiro spec

## Rules to respect (official)
- Under 3 minutes, public on YouTube or Vimeo, in English (captions for Nepali).
- Show the project working on **live Bee data**; mentioning Bee isn't enough.
- No third-party trademarks, music or footage without permission. No Alexa+ logo.
- **Don't use YouTube conversations or any third-party clips** (copyright, and it wouldn't be live Bee data).
