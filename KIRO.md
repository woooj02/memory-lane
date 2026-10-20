# Kiro, for the AWS Builder add-on ($5k)

The rules count "Kiro in the dev workflow", and an organizer confirmed Kiro qualifies on its
own (forum 45321). It has to be real use, so Kiro builds one feature end to end: **consent and
control** (a notice for visitors, pause, real delete), from the spec in
`.kiro/specs/consent-and-control/`. About 1 to 1.5 hours. It's the feature the trust story needs,
and nothing else depends on it, so Kiro can build it while we test on the device.

## Set up (15 min)
1. Download the Linux installer from https://kiro.dev/downloads (Ubuntu 24 is supported) and install it.
2. Open Kiro and sign in (GitHub or Google is fine).
3. **File → Open Folder** → `~/Projects/hackathons/amazon-2026/memory-lane`.
4. Kiro reads `.kiro/steering/` (product, tech, structure) on every request. In the Kiro panel,
   check that the 3 steering files and the "Tests on save" hook are listed.

## Build the feature (about 1 hour)
Any time (it doesn't need the watch). Do it before filming: the video shows the notice.
1. Open `.kiro/specs/consent-and-control/tasks.md`. Click **Start task** on task 1, then 2, 3, 4, 5.
   Review each diff before accepting.
2. The hook runs `./run.sh test -x -q` whenever Kiro saves a Python file. Every task should end green.
3. If Kiro asks to change the requirements, let it. Editing the spec is part of the workflow.

## Capture for the submission (5 min)
Screenshots of: the spec with tasks ticked, a task running, the hook's test output, and the
finished notice and pause controls. They go into the product feedback below and into
the Devpost gallery.

## Write-up (paste into PRODUCT_FEEDBACK.md → Kiro)
- **Used for:** spec-driven development of consent and control (requirements → design → 5 tasks),
  steering files for product rules (evidence-only cards, no health advice), and a test-on-save hook.
- **Worked well / needs work / onboarding / again?** Fill in from the session.
