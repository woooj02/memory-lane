# First real test with Mom's Apple Watch (planned for Sunday)

Goal: by the end, we know whether Bee captures Nepali well enough, and the app
runs on her real day. About 45 minutes plus some talking time.

## Before you start
- Mom has said yes to wearing it and being recorded for a few days, and the
  people she talks to on camera know too.
- The watch is charged. The iPhone it's paired with is nearby and on wifi.

## 1. Phone and watch (10 min)
1. On the paired iPhone, check the watch software: Watch app → General →
   About. It needs **watchOS 10 or later**. The iPhone needs **iOS 17.6+**.
2. Install **Bee - Your Personal AI** from the App Store. Create a Bee account
   (yours, or one just for this; not something tied to her other accounts).
3. Open the Watch app → scroll to Bee → **Install** on the watch.
4. In the Bee app: Settings → tap the **app version 5 times** → Developer Mode
   on. (Organizers confirmed it only appears after a device is paired.)
5. If Wrist Detection would lock the watch when it's off her wrist and you want
   it to sit on a table: Watch app → Passcode → Wrist Detection off. **Turn it
   back on before returning the watch.**

## 2. Record a test (5 min)
1. Start a recording on the watch (Bee app on the watch).
2. Mom talks normally in Nepali for about a minute with you: more than 50
   words, real things (a phone call she had, plans for the week).
3. Stop it and wait a few minutes for Bee to process it. It should show up in
   the Bee app.

## 3. Computer (15 min)
```bash
nvm use 20                             # node 20 is already installed; 14 is too old for bee
npm install -g @beeai/cli
bee login                              # approve on the iPhone
cd ~/Projects/hackathons/amazon-2026/memory-lane
./check-bee.sh                         # all PASS?
```

`./check-bee.sh` prints the first lines of her newest transcript and how
much of it is Nepali script. Then check the newer Bee data Memory Lane uses:
```bash
cd ../bee-cli-python && ./venv/bin/python -m beecli doctor && cd ../memory-lane
bee facts list --json | head -c 600; echo
bee photos list --json --limit 2 | head -c 600; echo     # keep these two: their shape isn't documented
```

## 4. The decision
Read the lines it printed (you understand Nepali):

| What you see | Decision |
|---|---|
| Nepali script, mostly what she said | **GO.** Continue to step 5. |
| Nepali script, but many wrong words | Try one more recording somewhere quiet. Still bad → fallback. |
| Hindi or romanized, or nonsense | **Fallback:** you are the user and speak English; the pitch stays "built for parents like mine". Set `PARENT_LANG=en PARENT_LANG_NAME=English PARENT_NAME=<your name>` in `.env`. |
| Nothing shows up | Check Developer Mode, `bee login`, and that the recording synced in the app. |

## 5. Run it on her day
```bash
cp .env.example .env     # put your TOGETHER_API_KEY in it
./run.sh compare --bee <id>   # id from `bee conversations list`; 5 models on her real conversation
```
Open the file it names (`data/compare-….md`). You read Nepali, so pick the
model whose English matches what she actually said and whose questions make
sense, then set `TOGETHER_MODEL=` to it in `.env`. (Speed and cost are in the
table at the top.) Then:
```bash
./run.sh
```
- Open http://127.0.0.1:8110/family → **Sync from Bee**. Each conversation
  should show the Nepali beside the English, and 1–3 questions.
- Medicine questions appear under **Waiting for your OK**: check them against
  the doctor's words, then Approve or Remove.
- Remove any question that's wrong. Note anything odd in `FRICTION_LOG.md`.
- In the evening, open http://127.0.0.1:8110/ with Mom and do the practice
  (keys: 1 remember, 2 hint, 3 forgot, N next). `/family` → **Reset tonight's
  practice** lets you run it again.
- `./check-bee.sh live` shows lines arriving in real time while she talks.

## 6. Collect demo material (over the next days)
- 4–6 real, ordinary conversations a day: a phone call, a meal, a visit.
  For the video, prefer staged everyday talk over private conversations.
- Film one evening practice on a tablet or laptop (her hands, the screen,
  her voice answering), with her permission.

## Returning the watch
- Bee app: delete the recordings you don't need and sign out.
- Remove Bee from the watch. Wrist Detection back on.
