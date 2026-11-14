# Model Forensics dashboard

A public, results-first explorer for the study's hypotheses, initial inputs, and complete observable transcripts. The Vue/TypeScript front end is hosted on Cloudflare Pages. The transcript viewer is read-only; the existing Pages Functions and D1 annotation records are retained.

The overview includes a grouped bar chart of concealment rates: baseline, then H0–H4 with separate negative and positive arms. It uses the recorded trial counts, a common 0–100% axis, and a dashed baseline reference. Bar labels show rates; hover or focus reveals exact counts, and selecting a bar opens its experiment. On small screens the chart scrolls horizontally.

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

## Verification

```sh
bun test
bun run build
bun run verify:data
# With the local Cloudflare preview running, and Chrome installed:
bun run test:browser
```

The data verification compares every transcript's full text, hash, displayed messages, final submission, and outcome with the original viewer export. Browser checks include the largest transcript, search and expansion, full-width desktop/mobile layouts, and the absence of note controls or annotation polling. `scripts/smoke.ts` uses Chrome on macOS; adjust its executable path for other systems.

## Update the dashboard through GitHub

Edit the `dashboard/` source on a branch and submit a pull request. The GitHub Actions workflow checks types, tests the annotation API, builds the site, and verifies imported data. Configure branch protection in GitHub if checks should be required before merging.

This project uses direct Cloudflare deployment, so no Cloudflare GitHub App connection is required. After merging and pulling `main`, a maintainer with Cloudflare access publishes the updated site with `bun run deploy`. GitHub commits alone do not change the live site. Native Git integration or an Actions deployment can be added later if automatic publishing is wanted.

To update the study, replace the public export at `studies/main/reports/viewer.html`, its companion `viewer-laptop.zip`, and the published report files. The preprocessing script recreates the site's data during the build; generated JSON is intentionally not committed. Study runs come only from the public viewer and published reports, never `sealed/` or API credentials. Separately labeled temporary examples come from the public archive sources described below. Full transcript text is preserved; display previews do not change source data.

The site loads an index first and individual experiment/transcript files on demand. The original ZIP remains available as a download. Existing annotation records remain keyed to run IDs and transcript hashes.

## Cloudflare configuration

- Project: `model-forensics-vncntt`
- Production branch: `main`
- Root directory: `dashboard`
- Build command: `bun run build`
- Output directory: `dist`
- Build environment: `BUN_VERSION=1.4.4`, `NODE_VERSION=24`
- D1 binding: `DB` → `model-forensics-annotations`

The root directory, build command, and output settings above also describe the configuration to use if Git integration is enabled later. They are handled locally by `bun run deploy` for the current direct-upload deployment.

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
