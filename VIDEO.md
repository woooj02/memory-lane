# Demo video plan (under 3:00)

Judges may score from this video alone, and aren't required to watch past 3:00.

**The story in one line:** her day, given back to her, in her own language.
Three promises, and every scene serves one of them:
1. **She remembers her day.** Evening practice built from her real conversations.
2. **She keeps her word.** What she promises out loud lands in Bee as a reminder.
3. **Her family has her back.** Every Nepali line in English, and medicine questions checked first.

The video follows **one day**, morning to night. It is not a feature tour: if a feature doesn't
move that day forward, it stays out (facts and Alexa+ get a few seconds at the end).

It must also prove, fast:
- **Live Bee data** (Stage 1 is pass/fail on this): the Bee app with today's date, and lines arriving live.
- **A real person and a real need** (Impact, Idea).
- **Non-trivial tech** (Tech, the first tie-breaker): live stream, real-time reminders, grounded questions, MCP.

Record at 1920×1080. Browser zoom 125% on the family page, 100% on the evening screen (sized for
an Echo Show). English narration in your voice, with English captions under all Nepali. No music
with lyrics; no third-party music, footage or logos; no Alexa+ logo ("Simulated Alexa+" text is fine).

## The opening number (sourced)
**"5.6 million Americans over 65 don't speak English very well. My mom is one of them."**
Source: U.S. Census Bureau, American Community Survey 2024 1-year, table B16004 (age 65+, speak
English less than "very well": 5,565,363 of 61.2 million, about 1 in 11). Put the source in small
text on screen and in the Devpost description. Use no other statistics, and never imply it
treats memory loss: it's practice.

## How judges follow the Nepali
The evening screen has a language switch (top right, or key **L**): नेपाली / नेपाली + English /
English. Use **नेपाली + English** for most of the evening, one short shot in Nepali only, and one
"same screen, now in English" beat. The family page is always English beside Nepali.

## Storyboard

| Time | Scene | On screen | Narration / caption |
|---|---|---|---|
| 0:00–0:12 | **Her** | Mom at the table, the pink watch on her wrist. Text: "5.6 million Americans over 65 don't speak English very well." (source small) | "My mom is one of them. She's in her sixties, she speaks only Nepali, and lately the details of her day slip away." |
| 0:12–0:20 | **Consent, said plainly** | She shows a visitor the `/notice` card on her phone (Nepali + English). | Caption: "Everyone she talks to knows Bee is listening. Pause and delete are one tap away." |
| 0:20–0:45 | **Morning: her sister calls** | Speakerphone call with her sister. Cut to `/family` → **Heard just now**: Nepali lines arrive live, English fills in under each. **Proof shot (2s):** the Bee app's conversation list with today's date. | "Her Apple Watch runs Bee. Memory Lane listens to Bee's live stream, so I can follow a conversation I couldn't understand before." Caption: `bee stream → live lines → English` |
| 0:45–0:58 | **She keeps her word (the wow beat)** | She says "हुन्छ दिदी, म आइतबार फोन गर्छु" (I'll call you Sunday). Seconds later: ⏰ **In her Bee · Sun 9:00 AM** appears on /family, then the reminder on her iPhone. | "She promised to call back on Sunday. Before she's even hung up, it's a reminder in her Bee." Caption: `real time → bee todos create --alarm-at` |
| 0:58–1:15 | **Midday: the doctor** | /family → **Waiting for your OK**: "What did the doctor say about the new tablet?" beside the doctor's exact words. Click **Approve**. | "Her day becomes a few questions, each tied to the exact words it came from. Anything about medicine waits until I've checked it." |
| 1:15–2:05 | **Evening: she remembers** | The evening screen (Simulated Alexa+ · Echo Show), **नेपाली + English**. The day timeline at the top. It reads the question aloud (in my voice, recorded on /family). Q1 she remembers → green. **Photo question**: her photo from the park, "Who were you with?" → hint → "Maya". Q3 she forgets → the answer with her sister's actual words. Press **L**: the same screen in English. | "In the evening she walks back through her own day, in Nepali, in my voice. A hint if she's stuck. If she forgets, she hears the words that were said to her. What she misses comes back tomorrow." |
| 2:05–2:15 | **End of practice** | "4 of 6", her promises, **Remind me in Bee** already ✓. Her smile. | "Four of six, on her own." |
| 2:15–2:40 | **How it's built** | `/how`: the pipeline with live counts. Quick cuts: the MCP panel (key **M**) with `start_evening_practice` / `record_recall`; "Teach Bee about her" saving a fact; the open-source library's README. | "Bee's live stream, transcripts, facts, photos and todos, through an open-source Python client we built. Open models on Together AI for translation and questions. The evening screen is an Alexa+ add-on: an MCP server any Alexa+ device or MCP client can run." |
| 2:40–2:55 | **Close** | Mom at the screen, or her hands on it. Title: सम्झना · Memory Lane. | "For every parent whose day happens in a language their apps don't speak." |

Timing check: about 2:55. If it's long, trim the "How it's built" cuts first, but keep at least 10 seconds of it.

## Before recording
- Real Bee data from her days (`BEE_MODE=cli`). For backup takes, the sample day (`BEE_MODE=demo LLM_PROVIDER=mock`) looks the same, and **Play the morning call live** on /family fires the real-time reminder.
- Record the evening questions in your voice on /family (**🎙 Ask it in your voice**) before filming.
- On /family, press **Reset tonight's practice** before each take of the evening.
- Open the evening screen at `/?lang=both`. Keys: **1** remember · **2** hint · **3** forgot · **N/Enter** next · **R** read aloud · **V** auto read-aloud · **L** language · **M** MCP panel.

## Shots to collect (Sun–Tue)
- [ ] Mom showing the /notice card to someone (consent, 0:12)
- [ ] Speakerphone call with her sister where she promises something with a day (0:20–0:58)
- [ ] iPhone: the Bee app's conversation list with today's date (proof)
- [ ] iPhone: the reminder that was created, with its alarm
- [ ] A visit or doctor-style conversation with an instruction (staged, everyday)
- [ ] A photo she takes during a conversation (for the photo question)
- [ ] Screen recordings: /family live feed; the whole evening practice, 2–3 takes
- [ ] Mom's hands or face at the screen during practice (with her OK)
- [ ] /how page, slow

## Rules to respect (official)
- Under 3 minutes, public on YouTube or Vimeo, in English (captions for Nepali).
- Show the project working on **live Bee data**; mentioning Bee isn't enough.
- No third-party trademarks, music or footage without permission. No Alexa+ logo.
- **Don't use YouTube conversations or any third-party clips** (copyright, and it wouldn't be live Bee data).
