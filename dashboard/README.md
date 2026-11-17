# Model Forensics dashboard

A public, results-first explorer for the study's hypotheses, initial inputs, and complete observable transcripts. The Vue/TypeScript front end is hosted on Cloudflare Pages. The transcript viewer is read-only; the existing Pages Functions and D1 annotation records are retained.

The overview uses a static Matplotlib chart: orange baseline, red negative arms, and green positive arms for H0–H4, on a 0–100% concealment axis. Every bar has a two-sided 95% Wilson confidence interval. The baseline remains 20/60 (22.7–45.9%). Once the fixed follow-up is finalized, each H0–H4 rate pools the original ten slots and twenty additional slots with the identical frozen prompt and model settings. Original ten-trial screening scores remain unchanged and are labeled separately from the pooled rate estimates. SVG and PNG exports and their source counts, intervals and experiment IDs are committed in `src/assets/plots/`. Data verification checks those values and the image hashes to catch stale or mismatched plots.

The November 17 follow-up is run from the project root with `python scripts/run_hypothesis_followup.py run --workers 100`. It creates ten separate approved twenty-slot pilot experiments, preserves completed slots and retry history, and reports each completed arm. After all 200 additional slots are completed and classified, `python scripts/finalize_hypothesis_followup.py` verifies source hashes, adds the public transcripts and results report to the offline viewer and ZIP, and preserves the historical exports. Then regenerate the dashboard data and chart as described below. The importer rejects partial follow-up publication, duplicate slots and unresolved outcomes. Raw source batches remain separately accessible; hypothesis pages show all thirty trials per direction.

## Current focus and combination archive

The main viewer covers only the baseline and H0–H4: 360 trials, including the 60-trial baseline and 30 trials per hypothesis direction. Its report selector and results download use the same scope. The dotted horizontal graph line marks the 33.3% baseline. `research-focus.json` at the project root records the active research scope.

The separate `/#/combinations` page preserves all 26 combinations and 520 trials, with round filters, original scores, prompts and transcripts. Archive reports are under `/#/methods?scope=archive`; combination notes live in project-root `archive/`. Original experiment/run IDs and evidence hashes are preserved. The full historical ZIP remains available from the archive. The two JSON downloads (`baseline-h0-h4-results.json` and `combination-archive-results.json`) contain disjoint source batches.

## Development

Requires Bun 1.4.4 and a recent Node.js version.

```sh
cd dashboard
bun install
bun run preprocess
bun run dev
```

To run the retained annotation API alongside the application:

```sh
bun run build
bun run db:local
bun run dev:cloudflare
```

Open the URL printed by Wrangler (normally `http://localhost:8788`). `bun run dev` is a front-end preview; use the Cloudflare preview above when testing shared annotations.

## Regenerate the plot

After updating the study data, regenerate the Matplotlib SVG and PNG before publishing:

```sh
bun run preprocess
python3 -m venv .venv-plot
.venv-plot/bin/python -m pip install -r scripts/requirements-plot.txt
.venv-plot/bin/python scripts/plot-results.py
bun run verify:data
```

Python is needed only to regenerate the committed images; normal site builds use the existing exports.

## Verification

```sh
bun run build
bun test
bun run verify:data
# With the local Cloudflare preview running, and Chrome installed:
bun run test:browser
```

The data verification compares every transcript's full text, hash, displayed messages, final submission, and outcome with the original viewer export. Browser checks include the largest transcript, search and expansion, full-width desktop/mobile layouts, and the absence of note controls or annotation polling. `scripts/smoke.ts` uses Chrome on macOS; adjust its executable path for other systems.

## Update the dashboard through GitHub

Edit the `dashboard/` source on a branch and submit a pull request. The GitHub Actions workflow checks types, tests the annotation API, builds the site, and verifies imported data. Configure branch protection in GitHub if checks should be required before merging.

This project uses direct Cloudflare deployment, so no Cloudflare GitHub App connection is required. The user-owned copy is configured in `personal-hosting.json`: `model-forensics-jabezhu0617` in account `c861f74b01dff55e0c5dde46159bc3e3`, production branch `main`. After signing in with `bunx wrangler login`, run `bun run deploy` to build, verify, and publish the current read-only viewer. The deploy script stages only public assets in an isolated directory, with no Functions or D1 binding. Each release is recorded in the ignored project-root `build/personal-deployment.json`.

GitHub commits alone do not change the live site. Native Git integration or an Actions deployment can be added later if automatic publishing is wanted. The original `model-forensics-vncntt` project remains separately configured in `wrangler.jsonc` and uses `bun run deploy:original` with its owner's Cloudflare access. Its database and annotation API are not part of the user-owned static copy.

To update the study, replace the public export at `studies/main/reports/viewer.html`, its companion `viewer-laptop.zip`, and the published report files. The preprocessing script recreates the site's data during the build; generated JSON is intentionally not committed. Study runs come only from the public viewer and published reports, never `sealed/` or API credentials. Separately labeled temporary examples come from the public archive sources described below. Full transcript text is preserved; display previews do not change source data.

The site loads an index first and individual experiment/transcript files on demand. The original ZIP remains available as a download. Existing annotation records remain keyed to run IDs and transcript hashes.

## Original Cloudflare configuration

- Project: `model-forensics-vncntt`
- Production branch: `main`
- Root directory: `dashboard`
- Build command: `bun run build`
- Output directory: `dist`
- Build environment: `BUN_VERSION=1.4.4`, `NODE_VERSION=24`
- D1 binding: `DB` → `model-forensics-annotations`

The root directory, build command, and output settings above also describe the configuration to use if Git integration is enabled later. They are handled locally by `bun run deploy:original` for the original direct-upload deployment.

The database ID in `wrangler.jsonc` is configuration, not a secret. OAuth/API credentials belong in the local Cloudflare login or hosting settings and must not be committed.

Apply schema changes before deploying code that depends on them:

```sh
bun run db:remote
```

## Retained annotation data

The viewer no longer displays shared notes, add-note buttons, or selection-to-annotation controls, and it does not poll the annotation API. Existing notes and their history remain in D1; removing the interface does not delete those records. The server API, migrations, and API tests are retained.

Back up D1 separately from the Git repository. Existing records can be retrieved with `GET /api/annotations?run=RUN_ID`; append `include_deleted=1` to include removed records.

## Temporary archive transcripts

The **Temp transcripts** navigation item opens public examples with explicit reasoning, assistant output, system/user prompts, and tool-call/result colors. These are separate from all study totals, hypotheses, and scores. Archive status is shown as recorded: importing a full log does not imply that its run completed the task.

Source logs live in `sources/temporary/`, with provenance and SHA-256 checksums in `manifest.json`. The build verifies each checksum, parses the archive's explicit section headings, and exports each example lazily under `public/data/runs/`, plus the original byte-for-byte log under `public/downloads/temporary/`. Reasoning is identified only by a `REASONING` source section; ordinary assistant text is never reclassified by its wording. Full log downloads include all framing, setup metadata, and final results.

To add an example, save its original `.log` file in that folder and add an entry to the manifest with a unique `temp-` ID, model, scenario, run label, source URL, pinned archive revision, and SHA-256 hash. Then run `bun run build` and `bun test`. Remove its manifest entry to remove it from the next build.
