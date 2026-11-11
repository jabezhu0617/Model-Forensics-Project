# End-of-day routine

When the user says “I’m done for the day” or otherwise signals they are wrapping up for the day, first ask, “Are you finished with this session?” Wait for their answer. If they confirm, do both of the following:

1. Prepare the code changes for a push. Tell the user which changes would be pushed, where they would go, and what checks passed or remain open. Wait for the user’s explicit green light for that push. Session confirmation alone does not authorize it. If there are no changes to push, say so.
2. Update the project-root `HANDOFF.md` for the next session with completed work, outstanding decisions, and the next concrete step. Do this even if there is nothing to push or push approval is still pending. If the user later approves the push, verify it and update the handoff with the published commit or any blocker.

## Push summaries

Before each push, inspect the outgoing diff. Give the user an itemized summary that names the files, explains what changed in each and what difference it makes, and includes concrete examples or result counts where relevant. Identify the destination and outgoing commits, report the checks performed, and distinguish published material from related local-only artifacts when that affects what the user will find on GitHub.
