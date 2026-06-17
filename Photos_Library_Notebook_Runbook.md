# Photos Library Metadata-Based Ultimate Thorough Merge — Notebook Runbook

> **重要：這個 Notebook 不是從頭到尾依序執行的 Notebook。不要使用 `Run All`。**  
> 它包含多種彼此不同的 scenario；有些 Cell 會覆寫 `Latest.tsv`，有些 Cell 依賴上一個 Cell 建立的變數。  
> 每次只按照下面某一個 recipe 執行，並且一律用 Cell 的標題辨識，不依賴 Cell number。

---

## 0. 目前已確認的 checkpoint（2026-06-17 約 14:52）

Fresh rebuild 後的 `current_default` inventory：

- assets: **95,469**
- albums: **6,042**
- folders: **35**
- assets without unique ID: **0**
- duplicate unique ID groups: **0**

股票 duplicate cleanup：

- 執行過的 deletion manifest：**26 jobs**
- `Post-delete audit — verify deleted albums absent and keeper albums intact`：
  - Fully passed: **26**
  - Failed: **0**
  - Delete UUID absent: **26**
  - Keepers present/path/title/count/checksum correct: **26**
- 重新產生股票 strict deletion manifest：
  - Strict delete rows: **0**
  - Candidate groups reviewed: **43**

最新 `DeleteDuplicateAlbumsCandidatesLatest.tsv` 的 43 groups：

- **38** groups：`OUTSIDE_TARGET_KEEP_FOLDER_PATH`
  - Backup canonical path `NSFW`: 34
  - Backup canonical path `NSFW / AV`: 4
- **2** 股票 groups：`CURRENT_KEEPER_COUNT_0`
  - 都是 `WHITESPACE_ONLY_DIFFERENCE`
  - 同 membership，但 raw title whitespace 無法唯一符合 Backup，因此安全跳過
- **1** NSFW group：`CURRENT_KEEPER_COUNT_0`
- **1** group：`EXCLUDED_TITLE` (`#給資料夾置頂用`)
- **1** group：`BACKUP_MATCH_COUNT_2` (`台北捷運地圖`)
- `READY_TO_DELETE`: **0**

這代表「股票這一輪的 strict auto-delete 已清空」，**不代表整個 Library 沒有其他 duplicates**。

---

## 1. 不可違反的操作規則

1. **不要 Run All。**
2. 每次 scenario 的第一步都是執行：
   - `Imports and Settings`
   - `Load or build inventories — unique ID generation / validation included`
3. Photos Library 只要被 Photos、PhotoKit App、HashPhotos 或人工操作修改過，`inventory_current` 就立刻變成 stale。
4. 寫入 Photos 之後，做任何正式判斷前都要 fresh rebuild `current_default`。
5. Backup inventory 通常可用 cache；除非 Backup Library 本身更換或重新解析，否則不要重建 Backup。
6. `DeleteDuplicateAlbumsManifestLatest.tsv` 和 `RepairManifestLatest.tsv` 是不同用途，不能混用。
7. `Latest.tsv` 會被覆寫。需要追溯時使用 `archive/` 的 timestamped copy。
8. `Post-delete audit — verify deleted albums absent and keeper albums intact` 必須讀到**實際執行過的 deletion manifest**：
   - audit 前不要重新執行 `Delete duplicate album shells — export strict PhotoKit manifest`
   - 若 `Latest` 已被覆寫，將 `AUDIT_MANIFEST_PATH` 指向對應的 archive manifest。
9. `inventory_backup` 是 2025-03-17 crash 前 Backup 的 ground truth，只適合判斷當時已存在的 album/path/membership。  
   Crash 之後合法新增的 assets/albums 不能因「Backup 沒有」就自動刪除。
10. 所有寫入 Photos 的動作都在 Swift PhotoKit App 進行；Notebook Cell 只讀 inventory、分析、輸出 TSV。

---

## 2. `Imports and Settings` 的三種設定

### 2.1 正常使用既有 cache

```python
USE_INVENTORY_CACHE = True
FORCE_REBUILD_INVENTORY_KEYS = set()
FORCE_RESELECT_LIBRARY_PATHS = False
```

### 2.2 Photos 剛被修改：只重建 Current Default

```python
USE_INVENTORY_CACHE = True
FORCE_REBUILD_INVENTORY_KEYS = {
    "current_default",
}
FORCE_RESELECT_LIBRARY_PATHS = False
```

### 2.3 Current Default Library 路徑改變

```python
USE_INVENTORY_CACHE = True
FORCE_REBUILD_INVENTORY_KEYS = {
    "current_default",
}
FORCE_RESELECT_LIBRARY_PATHS = True
```

執行完 fresh rebuild 後，正常下一輪應把：

```python
FORCE_REBUILD_INVENTORY_KEYS = set()
```

避免每次不小心重建。

---

## 3. 主要 Cell 地圖

| Cell title | 用途 | 主要輸入 | 主要輸出 | 是否改 Photos |
|---|---|---|---|---|
| `Imports and Settings` | 載入 helper、設定 cache/rebuild/path policy | 無 | 設定變數 | 否 |
| `Load or build inventories — unique ID generation / validation included` | 建立/載入 Backup 與 Current inventory | Settings | `inventory_backup`, `inventory_current` | 否 |
| `Whole-library folder/album membership comparison report` | 全庫 folder/album membership 對照報告 | 兩份 inventory | `reports/test2_folder_album_membership_comparison/...` | 否 |
| `Current Default — Duplicate Album Titles` | Current-only duplicate-title 診斷；包含 same/different membership | `inventory_current` | timestamped `current_duplicate_album_titles.tsv` | 否 |
| `Delete duplicate album shells — export strict PhotoKit manifest` | 用 Backup canonical path + exact cross-library membership 產生 strict delete candidate/manifest | 兩份 inventory | Candidate + executable Manifest + archive | 否 |
| `Post-delete audit — verify deleted albums absent and keeper albums intact` | 對已執行 deletion manifest 做 post-delete 驗證 | fresh `inventory_current` + executed manifest | `DeleteDuplicateAlbumsPostDeleteAuditLatest.tsv` | 否 |
| `Cross-library inventory diff summary report` | 建立 cross-library asset diff | 兩份 inventory | `diff_records` + summary report | 否 |
| `Status: ASSET_MISSING_FROM_CURRENT — DONE 20260615` | 檢查 Backup 有、Current 無的 assets | `diff_records` | console / optional report | 否 |
| `Repare folder-album relations in current default using info in backup: Find the info needed for reparments` | 指定一個 Backup folder，建立 album repair targets | 兩份 inventory | `backup_album_targets` | 否 |
| `Preflight check: Are target Backup albums already present elsewhere in Current Default?` | 在 export repair manifest 前找同名 album 是否已存在其他 path/root | `backup_album_targets`, inventories | preflight report | 否 |
| `Repare folder-album relations in current default using info in backup: Export TSV manifest for PhotosRepairMVP to actually repair them in Photots Liberary` | 產生 folder/album relation repair manifest | `backup_album_targets` | `RepairManifestLatest.tsv` + archive | 否 |
| `Optional helper: Backup album source snapshot under one folder` | 只列出 Backup 某 folder 內容，人工參考 | `inventory_backup` | console text | 否 |
| `Check: Backup vs Current album paths and asset counts, whole library` | 全庫 path/count/membership summary，或限制一個 root | 兩份 inventory | console table | 否 |
| `TEMP — Verify Job 1 duplicate deletion` | 只驗證歷史 Job 1 的固定 UUID | live Photos DB | console | 否 |
| `Test Playground` / `OLD Stuffs` | 臨時測試或封存程式 | 不固定 | 不固定 | 不納入標準流程 |

---

## 4. 三種 duplicate 檔案的意義

### 4.1 `current_duplicate_album_titles.tsv`

由 `Current Default — Duplicate Album Titles` 產生。

- **只看 Current**
- 不使用 Backup 判斷 canonical keeper
- 找所有 normalized title 重複的 Current album objects
- 同時包含：
  - exact same membership
  - different membership
- 適合做全體 duplicate 診斷
- 不是可直接執行的 delete list

### 4.2 `DeleteDuplicateAlbumsCandidatesLatest.tsv`

由 `Delete duplicate album shells — export strict PhotoKit manifest` 產生。

- 使用 **Backup 作 canonical ground truth**
- 只處理 Current 中：
  - normalized title 相同
  - complete cross-library membership 完全相同
  - Backup 恰好有一個相同 title+membership album
- Candidate 保留全庫符合「same-membership duplicate」前提的 groups 供 audit
- 非本輪 target keeper path 的 groups 會標示：
  - `decision = SKIP`
  - `reason = OUTSIDE_TARGET_KEEP_FOLDER_PATH`
- 它不是全 Library 的完整錯誤清單；它不包含：
  - same title but different membership groups
  - 沒有 duplicate title 的 misplaced album
  - missing assets
  - 所有 post-backup legitimate additions

### 4.3 `DeleteDuplicateAlbumsManifestLatest.tsv`

- 無 header
- 只含本輪 target path 中：
  - `decision = READY_TO_DELETE`
  - `role = DELETE`
- 這才是 Swift `PhotosRepairMVP` deletion App 讀取的 executable work order。

---

# 5. Execution Recipes

## Scenario A — 只載入資料、做一般 read-only 檢查

依序執行：

1. `Imports and Settings`
2. `Load or build inventories — unique ID generation / validation included`
3. 依需求執行任一 read-only report Cell

正常設定：

```python
FORCE_REBUILD_INVENTORY_KEYS = set()
FORCE_RESELECT_LIBRARY_PATHS = False
```

---

## Scenario B — Photos 剛被修改，fresh rebuild Current Default

適用：

- Swift PhotoKit App 剛寫入
- Photos/HashPhotos 人工刪除或移動 album/folder
- iCloud 同步後要重新盤點

依序執行：

1. 在 `Imports and Settings` 設：

```python
FORCE_REBUILD_INVENTORY_KEYS = {
    "current_default",
}
FORCE_RESELECT_LIBRARY_PATHS = False
```

2. 執行 `Imports and Settings`
3. 執行 `Load or build inventories — unique ID generation / validation included`
4. 檢查：
   - assets without unique ID = 0
   - duplicate unique ID groups = 0
5. 再執行所需 report/audit Cell

---

## Scenario C — 全 Library：以 Backup 對照 Current 的 read-only audit

這才是「全庫 backup-vs-current」流程；不是 delete candidate TSV 單獨代表全部。

依序執行：

1. `Imports and Settings`
2. `Load or build inventories — unique ID generation / validation included`
3. `Whole-library folder/album membership comparison report`
4. `Cross-library inventory diff summary report`
5. `Check: Backup vs Current album paths and asset counts, whole library`

若要檢查 Backup 有但 Current 無的 assets，再執行：

6. `Status: ASSET_MISSING_FROM_CURRENT — DONE 20260615`

說明：

- `Whole-library folder/album membership comparison report`：偏 folder/album relationship
- `Cross-library inventory diff summary report`：偏 asset-level cross-library diff
- `Check: Backup vs Current album paths and asset counts, whole library`：偏人工閱讀的 path/count/membership summary
- 三者互補，不能用 strict delete candidate 取代。

---

## Scenario D — Current-only duplicate diagnosis（不產生刪除工作）

依序執行：

1. `Imports and Settings`
2. `Load or build inventories — unique ID generation / validation included`
3. `Current Default — Duplicate Album Titles`

查看 timestamped：

```text
reports/test2_current_duplicate_album_titles/<timestamp>/current_duplicate_album_titles.tsv
```

重點欄位：

- `title_match_type`
- `group_membership_status`
- folder paths
- UUIDs
- counts/checksums

這一步只診斷，不決定 keeper，也不寫 delete manifest。

---

## Scenario E — 針對一個 target folder 產生 strict duplicate deletion manifest

例如只處理股票。

前提：

- 已 fresh rebuild `current_default`
- 已先看過 `Current Default — Duplicate Album Titles`

在 `Delete duplicate album shells — export strict PhotoKit manifest` 設：

```python
DELETE_DUP_TARGET_KEEP_FOLDER_PATH = "股票"
```

依序執行：

1. `Current Default — Duplicate Album Titles`
2. `Delete duplicate album shells — export strict PhotoKit manifest`

輸出：

```text
~/Downloads/PhotosRepairMVP_Inbox/DeleteDuplicateAlbumsCandidatesLatest.tsv
~/Downloads/PhotosRepairMVP_Inbox/DeleteDuplicateAlbumsManifestLatest.tsv
~/Downloads/PhotosRepairMVP_Inbox/archive/<timestamp>__delete_duplicate_*.tsv
```

Numbers review：

```text
decision = READY_TO_DELETE
role = DELETE
```

該列數必須等於 console 的：

```text
Strict delete rows: N
```

安全解讀：

- Candidate 可以包含其他 folder 的 `OUTSIDE_TARGET_KEEP_FOLDER_PATH`
- Manifest 只包含本輪 target folder 的 executable deletes
- `SKIP` / `REVIEW` 永遠不會進 Manifest

---

## Scenario F — Swift deletion App：先 dry run，再執行

先保存這一輪的 Candidate、Manifest 和 archive timestamp。

### Dry run

Swift：

```swift
executeDeletions = false
```

完整 dry run 理想結果：

```text
Passed: N
Already missing: M
Rejected: 0
```

且：

```text
N + M = Manifest rows
```

### Execute

Swift：

```swift
executeDeletions = true
```

`maxSuccessfulDeletionsPerRun`：

- `1`：每次 App run 最多新刪一個
- `25`：同一次 App run 逐筆做 25 個獨立 PhotoKit transactions；通常逐筆跳確認視窗

最終必須有：

```text
Deleted + Already missing = Manifest rows
Rejected = 0
```

此時**不要立刻重新執行 strict manifest exporter**，避免覆寫已執行 manifest。

---

## Scenario G — Post-delete audit（最重要的 deletion 驗證）

前提：

- `DeleteDuplicateAlbumsManifestLatest.tsv` 仍是剛才實際執行的 manifest
- 若已被覆寫，將 `AUDIT_MANIFEST_PATH` 改指向 archive 中的 executed manifest

依序執行：

1. `Imports and Settings`
2. `Load or build inventories — unique ID generation / validation included`
   - 必須 fresh rebuild `current_default`
3. `Post-delete audit — verify deleted albums absent and keeper albums intact`

全部成功的標準：

```text
Manifest jobs: N
Fully passed: N
Failed: 0
Delete UUID absent: N
Delete relationships absent: N
Keepers present: N
Keeper paths correct: N
Keeper titles correct: N
Keeper asset counts correct: N
Keeper membership checksums correct: N
```

這一步完成後，才可以重新執行 strict manifest exporter。

---

## Scenario H — 確認某 target folder 已清乾淨

Post-delete audit 完成後：

1. `Current Default — Duplicate Album Titles`
2. 在 `Delete duplicate album shells — export strict PhotoKit manifest` 保持同一 target，例如：

```python
DELETE_DUP_TARGET_KEEP_FOLDER_PATH = "股票"
```

3. 執行 `Delete duplicate album shells — export strict PhotoKit manifest`

完成標準：

```text
Strict delete rows: 0
```

Candidate 裡 target path 可能仍有安全 SKIP，例如 whitespace-only ambiguity；這不等於 executable duplicate 尚未刪除。

---

## Scenario I — 接著處理另一個 target folder

例如：

```python
DELETE_DUP_TARGET_KEEP_FOLDER_PATH = "NSFW"
```

或：

```python
DELETE_DUP_TARGET_KEEP_FOLDER_PATH = "NSFW / AV"
```

注意：`"NSFW"` 不會自動包含 `"NSFW / AV"`；目前是 exact path scope。

依序重做：

1. fresh rebuild Current Default
2. `Current Default — Duplicate Album Titles`
3. `Delete duplicate album shells — export strict PhotoKit manifest`
4. 人工 review Candidate
5. Swift full dry run
6. Swift execute
7. fresh rebuild Current Default
8. `Post-delete audit — verify deleted albums absent and keeper albums intact`
9. 再產生一次同 target strict manifest，確認 `Strict delete rows: 0`

---

## Scenario J — 修復 album/folder relationship（不是刪 duplicate）

這是「Backup 認為 album 應在某 folder，但 Current 不在該處」的 repair 流程。

**不要把這個流程和 duplicate deletion 流程混在一起。**

依序執行：

1. fresh rebuild Current Default
2. `Repare folder-album relations in current default using info in backup: Find the info needed for reparments`
   - 設定：

```python
TARGET_PARENT_FOLDER_PATH = "股票"
```

   - 產生 `backup_album_targets`
3. `Preflight check: Are target Backup albums already present elsewhere in Current Default?`
   - 先檢查同 title album 是否已存在 Root 或其他 folder
   - 若 preflight 發現散落 existing albums，停止，不要直接 export/run
4. `Repare folder-album relations in current default using info in backup: Export TSV manifest for PhotosRepairMVP to actually repair them in Photots Liberary`
   - 第一次務必：

```python
TARGET_START_INDEX = 0
MAX_ALBUMS_TO_EXPORT = 1
```

   - 確認單筆流程正確後才考慮 batch
5. Swift repair App 執行
6. fresh rebuild Current Default
7. 用下列 Cell 驗證：
   - `Whole-library folder/album membership comparison report`
   - `Check: Backup vs Current album paths and asset counts, whole library`
   - target-specific preflight/report

歷史教訓：

- 舊 repair App 曾在 target folder 找不到 album 時直接 create，而沒有妥善重用 Root/其他 folder 的 existing album，造成 duplicates。
- 未確認 Swift repair 版本已處理「reuse/move existing album」之前，不可 batch run。

---

## Scenario K — 檢查 missing Current assets

依序執行：

1. `Imports and Settings`
2. `Load or build inventories — unique ID generation / validation included`
3. `Cross-library inventory diff summary report`
4. `Status: ASSET_MISSING_FROM_CURRENT — DONE 20260615`

只有在明確需要輸出檔案時，才把：

```python
WRITE_MISSING_CURRENT_REVIEW_REPORT_FILES = True
```

---

## Scenario L — 只查看 Backup 某 folder 的 snapshot

依序執行：

1. `Imports and Settings`
2. `Load or build inventories — unique ID generation / validation included`
3. `Optional helper: Backup album source snapshot under one folder`

設定：

```python
TARGET_PARENT_FOLDER_PATH = "NSFW"
```

這個 helper 不被其他 Cell 依賴，也不驗證 repair。

---

## 6. 每次新增 Cell / 新 scenario 時，必須同步更新本 Runbook

任何新 Cell 加入後：

1. 在「主要 Cell 地圖」新增一列：
   - exact Cell title
   - 用途
   - inputs
   - outputs
   - 是否改 Photos
2. 若它形成新 workflow，新增一個 Scenario recipe。
3. 明確註記：
   - 必須先執行哪些 title
   - 會覆寫哪些 `Latest` files
   - 是否依賴 fresh inventory
   - 是否依賴上一個 Cell 產生的變數
   - 是否必須在 Swift App 寫入前/後執行
4. 不使用 Cell number 作永久文件，因為插入 Cell 後 number 會改變。
5. 完成重大階段後，更新最上方「目前已確認的 checkpoint」。

---

## 7. 快速判斷：我現在該跑哪一套？

- Photos 剛被修改 → **Scenario B**
- 想看整個 Library 與 Backup 差異 → **Scenario C**
- 只想列 Current duplicate titles → **Scenario D**
- 想產生某 folder 的 duplicate delete list → **Scenario E**
- 已經刪完，想確認沒刪錯 → **Scenario G**
- 想確認某 target 已無 executable duplicate → **Scenario H**
- 想處理下一個 folder → **Scenario I**
- 想修復 album 應放在哪個 folder → **Scenario J**
- 想查 Backup 有、Current 沒有的 assets → **Scenario K**

