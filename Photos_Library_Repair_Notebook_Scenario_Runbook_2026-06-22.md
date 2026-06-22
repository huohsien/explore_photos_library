# Photos Library Repair Notebook — Scenario Runbook

## Purpose and safety boundary

This runbook describes the intended use of `Photos_Library_Metadata_Based_Ultimate_Thorough_Merge--Test_2`.

The project is **Backup → Default Current restoration**, not a symmetric merge:

```text
Backup snapshot / ground truth
→ restore required structure and Backup membership into Default Current
→ preserve Default Current additions
```

- **Backup library:** ground truth and read-only for this project.
- **Default Current iCloud library:** the only library that repair apps or manual operations may change.
- Every Python Notebook section is read-only to Photos. The only high-risk stages are the paired Xcode/PhotoKit executors after a manifest has been reviewed.
- Do not run a Swift executor merely because a TSV exists. Read the matching notebook output and manifest first.

## Setup before every decision loop

1. Open the **Default Current iCloud Photos Library** in Photos before using any PhotosRepairMVP Swift executor.
2. In the notebook, run `SETUP-01`.
   - Review `FORCE_REBUILD_INVENTORY_KEYS`.
   - After any Photos change, rebuild `current_default` before trusting a post-change report.
   - Rebuild `backup_20250317` only when the Backup library itself has changed or the Backup inventory is intentionally refreshed.
3. Run `SETUP-02`.
4. Choose exactly one scenario below. Do not run unrelated repair/export cells in the same pass.

## Scenario A — Baseline restoration dashboard

**Question:** Is Backup-required information present in Default Current?

Run:

```text
SETUP-01 → SETUP-02 → REPORT-01
```

Optional date review:

```text
REPORT-01A
```

Outputs:
- `REPORT-01` writes the Backup-centric dashboard report.
- `REPORT-01A` writes a whole-second Taipei date-difference TSV.

No Swift app is involved.

## Scenario B — Diagnose duplicate titles anywhere in Default Current

**Question:** Which Current album objects share an exact or whitespace-equivalent title?

Run:

```text
SETUP-01 → SETUP-02 → REPORT-02
```

Output:
- A project-local TSV listing all Current duplicate-title groups.

Use this only for broad diagnosis. It does not decide whether folders are semantically equivalent and does not create a manifest.

## Scenario C — Delete strict duplicate album containers

**Question:** Are there duplicate Current album containers with exactly the same Current membership, where Backup uniquely identifies the keeper path?

Run:

```text
SETUP-01 → SETUP-02 → DELETE-01
```

`DELETE-01` creates:

```text
~/Downloads/PhotosRepairMVP_Inbox/
  DeleteDuplicateAlbumsCandidatesLatest.tsv
  DeleteDuplicateAlbumsManifestLatest.tsv
```

Decision:
- If the executable manifest has zero rows, do not run the Swift app.
- If it has rows, inspect `CandidatesLatest.tsv` first.

Swift execution recipe:
1. In Xcode, put the validated `PhotosRepairMVP_ContentView_DeleteDuplicateAlbums.swift` implementation into the project’s compiled `ContentView.swift`.
2. Set dry-run mode and a batch size of one:
   ```swift
   private let executeDeletions = false
   private let maxSuccessfulDeletionsPerRun = 1
   ```
3. Run the app. Confirm there are no rejected rows and the dry-run count matches the manifest.
4. Change only `executeDeletions` to `true`; keep the batch size at one for the first real run.
5. After execution, rebuild Default Current with `SETUP-01 → SETUP-02`, then run `DELETE-02` before overwriting the executed manifest.

The app deletes only album containers. It must never delete PHAssets.

## Scenario D — Move one existing Current album to a missing Backup canonical folder

**Question:** The Backup target AlbumPath is missing, but the same album already exists at root or another path and can be moved unchanged.

Run:

```text
SETUP-01 → SETUP-02 → REPAIR-01 → REPAIR-02 → REPAIR-03
```

Responsibilities:
- `REPAIR-01`: builds Backup canonical targets under `TARGET_PARENT_FOLDER_PATH`.
- `REPAIR-02`: narrow preflight for **MOVE_EXISTING_ALBUM_ONLY**. It identifies only strict `MOVE_READY` cases: one Current source object, one source path, exact Backup membership, and target path absent.
- `REPAIR-03`: exports only `MOVE_READY` rows.

Outputs from `REPAIR-03`:

```text
~/Downloads/PhotosRepairMVP_Inbox/
  MoveExistingAlbumsReviewLatest.tsv
  MoveExistingAlbumsManifestLatest.tsv
```

Swift execution recipe:
1. Use `PhotosRepairMVP_ContentView_MoveExistingAlbumsOnly_Batched.swift` in the compiled Xcode `ContentView.swift`.
2. Start in its dry-run mode with a one-job batch.
3. Run only after the manifest has nonzero rows and the review TSV matches the intended source and target paths.
4. Rebuild Default Current, then rerun the relevant audit/report.

Do not use this scenario when the canonical target album already exists. Moving a second same-title source into that folder would create another same-path album container.

## Scenario E — Create a missing Backup canonical album using existing Current assets

**Question:** A Backup album path is absent from Current and no existing Current album qualifies for a safe move.

Run:

```text
SETUP-01 → SETUP-02 → REPAIR-01 → REPAIR-02 → REPAIR-02B → REPAIR-04
```

`REPAIR-04` exports:

```text
~/Downloads/PhotosRepairMVP_Inbox/
  CreateMissingAlbumsReviewLatest.tsv
  CreateMissingAlbumsManifestLatest.tsv
```

Swift execution recipe:
1. Use `PhotosRepairMVP_ContentView_CreateMissingAlbums.swift` in the compiled Xcode `ContentView.swift`.
2. Dry run first with a small limit.
3. Confirm the review and manifest rows.
4. Execute a small verified batch.
5. Rebuild Default Current and rerun `REPORT-01` plus the applicable structure audit.

## Scenario F — Audit a root album that collides with a canonical target album

**Question:** Under the repair root selected in `REPAIR-01`, does Current have both:

```text
[ROOT_ALBUMS] / title
```

and:

```text
canonical folder / title
```

Run:

```text
SETUP-01 → SETUP-02 → REPAIR-01 → REPAIR-02C
```

`REPAIR-02C` is intentionally narrow:
- It looks only at **Current root albums** and the Backup canonical target path.
- It does not treat `HIDE / title` or other unrelated folder paths as action candidates.
- It writes project-local reports only; it does not write a Downloads manifest and does not use a Swift app.

Interpret the reported membership relation:

| Relation | Meaning | Current action |
|---|---|---|
| `EXACT_SAME_MEMBERSHIP` | Root and canonical albums contain the same Current assets. | Recheck with `DELETE-01`; if it exports a strict manifest, use the DeleteDuplicate Swift dry run/execution recipe. |
| `ROOT_SUBSET_OF_CANONICAL` | Every root member is already present in the canonical album. | Manual review. Deleting the root album container would not remove those assets, but it is an organizational decision. |
| `ROOT_SUPERSET_OF_CANONICAL` | Root contains every canonical member plus root-only members. | Add the root album’s contents to the canonical album manually in Photos, then rebuild Current and rerun `REPAIR-02C`. |
| `OVERLAP_WITH_BOTH_SIDES_UNIQUE` | Each album has members absent from the other. | Manually add root contents to the canonical album, rebuild Current, rerun `REPAIR-02C`, and review before deleting the root container. |
| `DISJOINT_MEMBERSHIP` | Same title, no shared members. | Do not merge or delete automatically. Treat as separate albums until manually reviewed. |

There is no dedicated cross-path additive-merge Swift executor in this notebook. Do not misuse `MoveExistingAlbumsOnly` or `DeleteDuplicateAlbums` for membership-mismatch cases.

## Scenario G — Review Backup structure below one repair root

**Question:** Are Backup folder paths and AlbumPaths under the selected root represented in Current?

Run:

```text
SETUP-01 → SETUP-02 → REPAIR-01 → REPAIR-02B
```

This is a read-only structural audit. It does not decide root-to-canonical membership merges and does not create a manifest.

## Scenario H — Review duplicate AlbumPaths in Backup and Current

**Question:** Are multiple album containers associated with the same AlbumPath?

Run:

```text
SETUP-01 → SETUP-02 → REPORT-07
```

This is a different problem from a root-to-canonical collision:
- Duplicate AlbumPath: two containers at the **same** path.
- Root-to-canonical collision: same title at **different** paths.

Use the existing AppleScript probe / additive-merge / delete workflow only for same-AlbumPath duplicate containers. Do not use it to merge `root / title` into `NSFW / title`.

## Scenario I — Post-repair verification

After any Photos change:
1. Rebuild Default Current using `SETUP-01 → SETUP-02`.
2. Run `REPORT-01`.
3. Run the scenario-specific audit:
   - Delete duplicate container: `DELETE-02`.
   - Move existing album: `REPAIR-02`, then `REPAIR-02B` if structural confirmation is needed.
   - Create missing album: `REPAIR-02B`, then `REPORT-01`.
   - Root-to-canonical manual merge: `REPAIR-02C`.

## Notebook section map

```text
SETUP-01   Imports, paths, rebuild controls
SETUP-02   Build/load inventories
REPORT-01  Backup-centric restoration dashboard
REPORT-01A Whole-second date-difference review
REPORT-02  Current duplicate title diagnosis
DELETE-01  Strict duplicate-album delete manifest
DELETE-02  Post-delete audit
REPORT-03  Cross-library inventory diff
REPORT-04  Assets missing from Current
REPAIR-01 Backup targets under selected repair root
REPAIR-02 Move-existing preflight only
REPAIR-02B Backup ground-truth structure audit
REPAIR-02C Root-to-canonical collision audit
REPAIR-03 Move-existing manifest export
REPAIR-04 Create-missing-albums manifest export
REPORT-05..07 Additional read-only reports
ARCHIVE-*  Historical cells; do not use for a new repair pass
```
