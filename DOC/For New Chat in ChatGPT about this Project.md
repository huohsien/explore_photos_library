# iCloud Photos Library Forensic / Metadata-Based Restoration — Project Handoff

請先完整讀完這份 handoff，再開始回答。這是長期跨多個 chat 的 Photos Library 修復專案

## Project 核心目標

有兩個 Photos Library：

1. **Backup / Ground Truth**

   * 2025-03 crash 前的非系統備份庫。
   * 是「原本應存在什麼」的 ground truth。

2. **Current Default / iCloud System Library**

   * crash 後、目前同步 iCloud、仍持續使用的主庫。
   * 有 crash 造成的 folder / album structure damage。
   * 也有 crash 後新增的 assets、albums、memberships，這些必須保留。

整個 project 不是把兩邊做 symmetric merge，也不是把 Current-only 東西刪掉。

真正規則是：

> Backup 裡原本存在的 assets、metadata、folder structure、album structure、album memberships，Current 都應完整保留或修復回來。
> Current 後來新增的 assets 或 albums 不因為 Backup 沒有就變成錯誤，更不能自動刪除。

## 已知 crash 後結構問題

Current 曾出現：

* Backup 原本的 folder 在 Current 消失；
* folder 消失後，某些 album 掉到 root；
* 某些 album 完全消失；
* 有些 album 尚在 Current，但位於錯誤 folder path；
* 有些 Backup album members 在 Current 對應 album 裡缺少；
* 同一 canonical AlbumPath 出現多個 Current album containers，造成 repair target ambiguous。

## 重要安全原則

```text
Inventory rebuild / cache
→ Read-only analysis/report
→ Preflight
→ Manifest export
→ Small verified execution batch
→ Fresh rebuild
→ Post-repair audit
```

* Python Notebook / osxphotos：只做 inventory、comparison、report、manifest export；不直接改 Photos。
* PhotosRepairMVP Swift / PhotoKit app：真正執行已核准 manifest，可能 move albums、create albums、add existing PHAssets。
* AppleScript：僅用於近期 duplicate album container cleanup；它只作用於目前 Photos app 已開啟的 library，不能自己辨識或切換 .photoslibrary。

不要把 title 當 album identity。

```text
Album identity = AlbumPath = folder path + album title
```

例如：

```text
[ROOT_ALBUMS] / Girls
HIDE / Girls
```

是兩個不同 AlbumPath，不能因為同名自動合併。

## Current primary files

```text
explorephotoslibrary.py
Photos_Library_Metadata_Based_Ultimate_Thorough_Merge--Test_2.ipynb
```

Notebook major sections：

```text
SETUP-01 / SETUP-02

REPORT-01 — Whole-Library Folder/Album Membership Comparison
REPORT-02 — Current Default Duplicate Album Titles
DELETE-01 / DELETE-02
REPORT-03 — Cross-Library Inventory Diff Summary
REPORT-04 — Assets Missing from Current Status

REPAIR-01 — Find Folder/Album Relationship Repair Information
REPAIR-02 — Preflight Existing Albums Elsewhere in Current
REPAIR-02B — Audit Backup Ground-Truth Album Structure
REPAIR-03 — Export MOVE_EXISTING_ALBUM_ONLY manifest
REPAIR-04 — Export CREATE_MISSING_ALBUM_WITH_EXISTING_ASSETS manifest

REPORT-05 / REPORT-06 / REPORT-07
```

## Main repair workflow

For each selected repair root:

```text
REPAIR-01
→ identify Backup ground-truth relationships and Current candidates

REPAIR-02
→ check whether matching Current albums already exist elsewhere
→ move existing album containers first when strict matching proves identity

REPAIR-03
→ export MOVE_EXISTING_ALBUM_ONLY manifest
→ execute in small PhotosRepairMVP batches
→ rebuild and audit

REPAIR-04
→ only after move-existing phase
→ create truly missing albums
→ add existing matching Current PHAssets
→ rebuild and audit
```

The order matters:

```text
Move existing matching albums first.
Create missing albums only after preflight proves there is no safely matching Current album to move.
```

## Asset identity

Cross-library asset matching uses `photo_library_asset_unique_id`.

Important decisions:

* original filename extension case is normalized:

  ```text
  .JPG / .jpg / .JPEG / .jpeg are equivalent
  ```
* filename stem is not lowercased;
* date is compared in Taipei local time, whole-second precision;
* file size and adjustment signature participate;
* SHA-256 is used only to resolve identity collisions;
* a normal file under `.photoslibrary/originals/` is a normal inventory asset even when `syndicated=True`;
* `syndicated=True` by itself does not mean asset missing.

## Main task currently pending: redesign REPORT-01

Do **not** modify `_ChangeType` or `compare_inventories()` as part of this work.

`_ChangeType` is the broad asset/object diff taxonomy used by `compare_inventories()`. It is separate from the structural preservation report.

The main repair queue should be the Backup-centric whole-library folder/album membership report:

```python
write_folder_album_membership_comparison_report(...)
```

Current old report statuses are:

```text
MISSING_ALBUM_IN_CURRENT
CURRENT_ONLY_ALBUM
MEMBERSHIP_DIFF
OK
```

This is not the correct Backup-centric model because:

```text
CURRENT_ONLY_ALBUM
```

is usually just a later Current addition and not a repair problem.

Also:

```text
MEMBERSHIP_DIFF
```

currently mixes two different conditions:

```text
A. Backup members missing in Current
   → real repair problem

B. Current has extra members not in Backup
   → normally harmless; no repair needed
```

## Immediate next steps

1. Inspect the current implementation of:

```python
write_folder_album_membership_comparison_report(...)
```

2. Propose a narrow refactor:

   * add formal REPORT-01 status definitions;
   * make Backup paths the primary review universe;
   * ignore Current additions as a defect;
   * split membership missing from harmless Current extras;
   * detect ambiguous Current AlbumPaths;
   * keep optional Current-only diagnostics outside repair queue;
   * update REPORT-01 Markdown/runbook explanation.

3. Before writing code:

   * explain input/output;
   * explain what changes and does not change;
   * explain risks;
   * explain expected new report behavior;
   * wait for explicit approval.

4. After approval:

   * generate downloadable replacement helper / notebook cell files;
   * do not paste long code in chat.

5. Run redesigned REPORT-01 and use its output to resume:

   * move-existing albums;
   * create genuinely missing albums;
   * repair missing Backup album members;
   * rebuild and audit after each batch.

## Working style rules

* Respond in Traditional Chinese unless user writes English.
* Do not invent results or say something is verified without fresh report evidence.
* Keep focus on restoring Current Default using Backup as ground truth.
* Do not treat Current-only additions as errors.
* Do not merge same-title albums across different AlbumPaths automatically.
* Keep risky operations small and screenshot/cell-guided.
* Before generating substantial code, explain the work and obtain confirmation.
* Provide downloadable code files by default rather than large pasted code.
* For Git commit requests, provide one complete copy-pastable shell command with `git add`, `git commit -m`, and correct trailing backslashes.
