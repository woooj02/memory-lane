# Hackathon playbook

Judges give each team 3–5 minutes. They score four things: a sharp problem, a
demo that works live, a story, and fit with the sponsor. Everything below
serves one of those.

## Before the event (T-minus a week)

- [ ] Read the rules and the judging rubric. **Write the rubric weights into
      `NOTES.md` in the project.** We build to the rubric.
- [ ] List every sponsor prize and its required tech. A sponsor prize is often
      easier to win than the main prize, and you can usually win both.
- [ ] Get the sponsor API keys and sandbox accounts set up *before* the clock starts.
- [ ] `./new.sh <event> <project> <port>` and deploy the empty app once, so the
      hosting path is proven early.
- [ ] Shortlist 3 ideas and score each 1–5 on: the one-sentence problem, the
      "wow" moment in the demo, sponsor fit, and whether we can build it in
      ~60% of the available time.

## Picking the idea

Good hackathon ideas share some traits:
- **One user, one painful job, one moment where the agent visibly does it.**
- The demo is something the judges can *watch happen*, not just read about. The
  tool-call trace in the UI is there for this reason.
- It uses the sponsor's tech in a way that would be hard to drop. Not a token
  API call bolted on at the end.
- No login screens, no settings pages, nothing the judges won't see.

## During the build

| Share of time | Goal |
|------|------|
| First 10% | The idea is locked. The scripted demo prompts are written down. |
| By 40% | **The ugly end-to-end version is deployed.** The happy path works live. |
| By 70% | Feature freeze. From here on, only polish, reliability and the pitch. |
| Last 30% | Demo video, README, rehearsals, `REPLAY=record` runs |

Rules:
- Deploy early and often (`./deploy.sh`). "Works on my laptop" isn't a demo.
- Every feature gets cut unless it shows up in the 3-minute demo.
- Keep the scripted demo prompts in `EXAMPLES` in `web/index.html`, so they're
  one click away on stage.

## The pitch (3 minutes)

1. **Problem (20s).** Who hurts, how much, and a concrete number.
2. **Live demo (90s).** One scripted path, starting at the wow moment. Narrate
   what the agent is doing while the trace fills in.
3. **How it works (30s).** One architecture sentence, plus what the sponsor
   tech does in it.
4. **Why now / what's next (20s).** Market size or the next user.
5. **Ask/close (10s).**

## Demo insurance

- [ ] Rehearse with `REPLAY=record`, then run the stage copy with `REPLAY=play`.
      The scripted prompts then return instantly even if venue wifi or the
      API is down.
- [ ] Record a backup screen capture of the full demo.
- [ ] Keep a phone hotspot ready.
- [ ] Set `CLAUDE_EFFORT=low` if the live demo feels slow. Rehearse the answers
      at that setting.

## Online (Devpost) submission checklist

- [ ] Public GitHub repo with an open-source LICENSE (MIT is already included)
- [ ] README: problem, demo link, screenshots, how to run, built with
- [ ] Hosted demo URL (`./deploy.sh` gives you https://NAME.91.99.162.43.sslip.io)
- [ ] Demo video **under the time limit** (often 3 min), public on YouTube
- [ ] Every sponsor prize you're eligible for selected on the form
- [ ] Submit **a day early**, then update. Devpost locks at the deadline.
