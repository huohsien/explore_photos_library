-- ============================================================
-- REPORT-07 — Probe → Additive Merge → Verify → Delete
-- Exact-Title Duplicate Albums (Generic Three-Stage Version)
--
-- Change ONLY this property for a title-only duplicate group:
-- ============================================================

property targetAlbumTitle : "宵夜"

-- ============================================================
-- IMPORTANT SCOPE
--
-- This script matches ALBUM TITLE exactly across the entire
-- currently opened Photos Library.
--
-- It does NOT understand folder paths.
--
-- Therefore, do NOT continue when the same album title exists
-- in more than one unrelated folder/path unless all matches are
-- intentionally part of the same merge.
--
-- Example:
--   "Girls" may exist both at root and under HIDE.
--   This title-only script would see all of them together.
--
-- Safety model:
--   Stage 1: Read-only probe and human confirmation.
--   Stage 2: Add memberships only; no deletion.
--   Stage 3: Delete source album containers only after a fresh
--            ID-level verification.
--
-- It never deletes media items.
-- ============================================================


-- ============================================================
-- HELPER: Return unique IDs from media items in album list.
-- ============================================================

on uniqueMediaIDsFromAlbums(albumList)
	tell application "Photos"
		set uniqueIDs to {}

		repeat with currentAlbum in albumList
			set currentItems to get media items of currentAlbum

			repeat with currentItem in currentItems
				set currentID to id of currentItem

				if uniqueIDs does not contain currentID then
					set end of uniqueIDs to currentID
				end if
			end repeat
		end repeat

		return uniqueIDs
	end tell
end uniqueMediaIDsFromAlbums


-- ============================================================
-- HELPER: Return IDs from one album.
-- ============================================================

on mediaIDsFromAlbum(theAlbum)
	tell application "Photos"
		set resultIDs to {}
		set currentItems to get media items of theAlbum

		repeat with currentItem in currentItems
			set end of resultIDs to id of currentItem
		end repeat

		return resultIDs
	end tell
end mediaIDsFromAlbum


-- ============================================================
-- HELPER: Count how many IDs in requiredIDs are absent from
-- availableIDs.
-- ============================================================

on missingIDCount(requiredIDs, availableIDs)
	set missingCount to 0

	repeat with requiredID in requiredIDs
		if availableIDs does not contain requiredID then
			set missingCount to missingCount + 1
		end if
	end repeat

	return missingCount
end missingIDCount


-- ============================================================
-- HELPER: Build a readable summary and master-choice labels.
-- ============================================================

on buildAlbumSummary(albumList)
	tell application "Photos"
		set summaryText to ""
		set choiceLabels to {}
		set maximumCount to -1
		set maximumIndexes to {}

		repeat with albumIndex from 1 to count of albumList
			set currentAlbum to item albumIndex of albumList
			set currentCount to count of media items of currentAlbum
			set currentID to id of currentAlbum

			set summaryText to summaryText & ¬
				albumIndex & ". " & currentCount & " items" & return

			set labelText to albumIndex & ". " & currentCount & ¬
				" items | " & currentID
			set end of choiceLabels to labelText

			if currentCount > maximumCount then
				set maximumCount to currentCount
				set maximumIndexes to {albumIndex}
			else if currentCount is maximumCount then
				set end of maximumIndexes to albumIndex
			end if
		end repeat

		return {summaryText, choiceLabels, maximumCount, maximumIndexes}
	end tell
end buildAlbumSummary


-- ============================================================
-- MAIN
-- ============================================================

tell application "Photos"
	activate

	with timeout of 60 * 60 seconds

		-- --------------------------------------------------------
		-- STAGE 1 — READ-ONLY PROBE
		-- --------------------------------------------------------

		set matchedAlbums to every album whose name is targetAlbumTitle
		set matchedAlbumCount to count of matchedAlbums

		if matchedAlbumCount is 0 then
			display dialog ¬
				"No album was found with the exact title:" & return & return & ¬
				targetAlbumTitle & return & return & ¬
				"Nothing was changed." ¬
				buttons {"OK"} default button "OK" ¬
				with icon stop ¬
				with title "Exact-Title Probe"
			return
		end if

		if matchedAlbumCount is 1 then
			set onlyAlbum to item 1 of matchedAlbums
			set onlyCount to count of media items of onlyAlbum

			display dialog ¬
				"Only one exact-title album was found." & return & return & ¬
				"Exact title: " & targetAlbumTitle & return & ¬
				"Albums found: 1" & return & ¬
				"Media count: " & onlyCount & return & return & ¬
				"There is nothing to merge or delete." ¬
				buttons {"OK"} default button "OK" ¬
				with icon note ¬
				with title "Already Consolidated"
			return
		end if

		set summaryBundle to my buildAlbumSummary(matchedAlbums)
		set albumSummary to item 1 of summaryBundle
		set choiceLabels to item 2 of summaryBundle
		set maximumCount to item 3 of summaryBundle
		set maximumIndexes to item 4 of summaryBundle

		set uniqueIDsBefore to my uniqueMediaIDsFromAlbums(matchedAlbums)
		set uniqueCountBefore to count of uniqueIDsBefore

		set totalMembershipRowsBefore to 0
		repeat with currentAlbum in matchedAlbums
			set totalMembershipRowsBefore to totalMembershipRowsBefore + ¬
				(count of media items of currentAlbum)
		end repeat

		set duplicateMembershipRows to ¬
			totalMembershipRowsBefore - uniqueCountBefore

		set probeText to ¬
			"READ-ONLY PROBE" & return & return & ¬
			"Photos must currently be showing the intended library." & return & return & ¬
			"Exact title: " & targetAlbumTitle & return & ¬
			"Albums found: " & matchedAlbumCount & return & ¬
			"Total membership rows: " & totalMembershipRowsBefore & return & ¬
			"Unique media items: " & uniqueCountBefore & return & ¬
			"Duplicate memberships across albums: " & ¬
			duplicateMembershipRows & return & return & ¬
			"Album counts:" & return & albumSummary & return & ¬
			"TITLE-ONLY WARNING:" & return & ¬
			"This includes every album with this exact title across the library." & return & ¬
			"Do not continue if unrelated folder paths are mixed together."

		set stageOneChoice to button returned of (display dialog ¬
			probeText ¬
			buttons {"停止，不做任何變更", "選擇主相簿並進入合併"} ¬
			default button "停止，不做任何變更" ¬
			cancel button "停止，不做任何變更" ¬
			with icon caution ¬
			with title "Stage 1 — Exact-Title Probe")

		if stageOneChoice is not "選擇主相簿並進入合併" then
			return
		end if


		-- --------------------------------------------------------
		-- CHOOSE MASTER ALBUM
		-- --------------------------------------------------------

		set masterAlbumIndex to 0

		if (count of maximumIndexes) is 1 then
			set proposedIndex to item 1 of maximumIndexes
			set proposedAlbum to item proposedIndex of matchedAlbums
			set proposedCount to count of media items of proposedAlbum
			set proposedID to id of proposedAlbum

			set automaticChoiceText to ¬
				"The largest album is unique." & return & return & ¬
				"Proposed master index: " & proposedIndex & return & ¬
				"Current media count: " & proposedCount & return & ¬
				"Album ID: " & proposedID & return & return & ¬
				"Use this album as the master?"

			set masterChoice to button returned of (display dialog ¬
				automaticChoiceText ¬
				buttons {"取消", "改為手動選擇", "使用這個主相簿"} ¬
				default button "使用這個主相簿" ¬
				cancel button "取消" ¬
				with icon caution ¬
				with title "Choose Master Album")

			if masterChoice is "取消" then
				return
			else if masterChoice is "使用這個主相簿" then
				set masterAlbumIndex to proposedIndex
			end if
		end if

		if masterAlbumIndex is 0 then
			set selectedChoices to choose from list choiceLabels ¬
				with title "Choose Master Album" ¬
				with prompt "Select exactly one album to retain as the master." ¬
				default items {item 1 of choiceLabels} ¬
				OK button name "使用所選相簿" ¬
				cancel button name "取消" ¬
				without multiple selections allowed

			if selectedChoices is false then
				return
			end if

			set selectedLabel to item 1 of selectedChoices

			repeat with labelIndex from 1 to count of choiceLabels
				if item labelIndex of choiceLabels is selectedLabel then
					set masterAlbumIndex to labelIndex
					exit repeat
				end if
			end repeat
		end if

		if masterAlbumIndex is 0 then
			display dialog ¬
				"STOPPED — no master album could be resolved." & return & ¬
				"Nothing was changed." ¬
				buttons {"OK"} default button "OK" ¬
				with icon stop ¬
				with title "Master Selection Failed"
			return
		end if

		set masterAlbum to item masterAlbumIndex of matchedAlbums
		set masterAlbumID to id of masterAlbum
		set masterCountBefore to count of media items of masterAlbum

		set sourceAlbums to {}

		repeat with currentAlbum in matchedAlbums
			if (id of currentAlbum) is not masterAlbumID then
				set end of sourceAlbums to currentAlbum
			end if
		end repeat

		set sourceAlbumCount to count of sourceAlbums


		-- --------------------------------------------------------
		-- STAGE 2 — ADDITIVE MERGE
		-- --------------------------------------------------------

		set mergeConfirmationText to ¬
			"ADDITIVE MERGE" & return & return & ¬
			"Exact title: " & targetAlbumTitle & return & ¬
			"Master index: " & masterAlbumIndex & return & ¬
			"Master before: " & masterCountBefore & " items" & return & ¬
			"Source albums: " & sourceAlbumCount & return & ¬
			"Expected master after merge: " & uniqueCountBefore & " unique items" & return & return & ¬
			"This stage only ADDS album memberships." & return & ¬
			"It does not delete albums or media items." & return & return & ¬
			"Continue?"

		set stageTwoChoice to button returned of (display dialog ¬
			mergeConfirmationText ¬
			buttons {"停止，不做任何變更", "開始只加不刪的合併"} ¬
			default button "停止，不做任何變更" ¬
			cancel button "停止，不做任何變更" ¬
			with icon caution ¬
			with title "Stage 2 — Confirm Additive Merge")

		if stageTwoChoice is not "開始只加不刪的合併" then
			return
		end if

		set submittedMembershipRows to 0

		repeat with sourceAlbum in sourceAlbums
			set sourceItems to get media items of sourceAlbum
			set sourceItemCount to count of sourceItems

			if sourceItemCount > 0 then
				add sourceItems to masterAlbum
				set submittedMembershipRows to ¬
					submittedMembershipRows + sourceItemCount
			end if
		end repeat

		delay 2

		set masterIDsAfterMerge to my mediaIDsFromAlbum(masterAlbum)
		set masterCountAfterMerge to count of masterIDsAfterMerge
		set missingAfterMerge to my missingIDCount(uniqueIDsBefore, masterIDsAfterMerge)

		if missingAfterMerge is not 0 then
			display dialog ¬
				"WARNING — additive commands were submitted, but verification failed." & return & return & ¬
				"Expected unique media IDs: " & uniqueCountBefore & return & ¬
				"Observed master count: " & masterCountAfterMerge & return & ¬
				"Required IDs still missing from master: " & missingAfterMerge & return & return & ¬
				"No albums were deleted." & return & ¬
				"Stop here and inspect the result." ¬
				buttons {"OK"} default button "OK" ¬
				with icon stop ¬
				with title "Stage 2 — Merge Verification Failed"
			return
		end if

		set mergeVerifiedText to ¬
			"MERGE VERIFIED" & return & return & ¬
			"Exact title: " & targetAlbumTitle & return & ¬
			"Master before: " & masterCountBefore & return & ¬
			"Membership rows submitted: " & submittedMembershipRows & return & ¬
			"Master after: " & masterCountAfterMerge & return & ¬
			"Expected unique media items: " & uniqueCountBefore & return & ¬
			"Required IDs missing from master: 0" & return & return & ¬
			"The source albums still exist." & return & return & ¬
			"Stop now, or continue to a fresh deletion verification?"

		set postMergeChoice to button returned of (display dialog ¬
			mergeVerifiedText ¬
			buttons {"停止，保留來源相簿", "重新驗證並進入刪除"} ¬
			default button "停止，保留來源相簿" ¬
			cancel button "停止，保留來源相簿" ¬
			with icon note ¬
			with title "Stage 2 — Additive Merge Complete")

		if postMergeChoice is not "重新驗證並進入刪除" then
			return
		end if


		-- --------------------------------------------------------
		-- STAGE 3 — FRESH VERIFICATION BEFORE DELETION
		-- --------------------------------------------------------

		set refreshedAlbums to every album whose name is targetAlbumTitle
		set refreshedAlbumCount to count of refreshedAlbums

		if refreshedAlbumCount is not matchedAlbumCount then
			display dialog ¬
				"STOPPED — nothing was deleted." & return & return & ¬
				"Album count changed after the merge." & return & ¬
				"Before: " & matchedAlbumCount & return & ¬
				"Now: " & refreshedAlbumCount ¬
				buttons {"OK"} default button "OK" ¬
				with icon stop ¬
				with title "Stage 3 — Fresh Verification Failed"
			return
		end if

		set refreshedMasterCandidates to every album in refreshedAlbums ¬
			whose id is masterAlbumID

		if (count of refreshedMasterCandidates) is not 1 then
			display dialog ¬
				"STOPPED — nothing was deleted." & return & return & ¬
				"The previously selected master album ID could not be resolved uniquely." ¬
				buttons {"OK"} default button "OK" ¬
				with icon stop ¬
				with title "Stage 3 — Master Verification Failed"
			return
		end if

		set refreshedMaster to item 1 of refreshedMasterCandidates
		set refreshedMasterIDs to my mediaIDsFromAlbum(refreshedMaster)
		set refreshedMasterCount to count of refreshedMasterIDs
		set refreshedMissingCount to my missingIDCount(uniqueIDsBefore, refreshedMasterIDs)

		if refreshedMissingCount is not 0 then
			display dialog ¬
				"STOPPED — nothing was deleted." & return & return & ¬
				"The master album no longer contains every required media ID." & return & ¬
				"Missing required IDs: " & refreshedMissingCount ¬
				buttons {"OK"} default button "OK" ¬
				with icon stop ¬
				with title "Stage 3 — Membership Verification Failed"
			return
		end if

		set refreshedSources to {}
		set sourceSummary to ""

		repeat with currentAlbum in refreshedAlbums
			if (id of currentAlbum) is not masterAlbumID then
				set end of refreshedSources to currentAlbum
				set sourceSummary to sourceSummary & ¬
					(count of media items of currentAlbum) & " items" & return
			end if
		end repeat

		set refreshedSourceCount to count of refreshedSources

		if refreshedSourceCount is not sourceAlbumCount then
			display dialog ¬
				"STOPPED — nothing was deleted." & return & return & ¬
				"Source album count changed unexpectedly." & return & ¬
				"Expected: " & sourceAlbumCount & return & ¬
				"Found: " & refreshedSourceCount ¬
				buttons {"OK"} default button "OK" ¬
				with icon stop ¬
				with title "Stage 3 — Source Verification Failed"
			return
		end if

		set deletionText to ¬
			"DELETE SOURCE ALBUM CONTAINERS" & return & return & ¬
			"Exact title: " & targetAlbumTitle & return & ¬
			"Master retained: " & refreshedMasterCount & " items" & return & ¬
			"Source albums to delete: " & refreshedSourceCount & return & ¬
			"Required media IDs missing from master: 0" & return & return & ¬
			"Source album counts:" & return & sourceSummary & return & ¬
			"This deletes only album containers." & return & ¬
			"It does NOT delete photos or videos." & return & return & ¬
			"Continue?"

		set deletionChoice to button returned of (display dialog ¬
			deletionText ¬
			buttons {"取消，保留來源相簿", "刪除來源相簿"} ¬
			default button "取消，保留來源相簿" ¬
			cancel button "取消，保留來源相簿" ¬
			with icon caution ¬
			with title "Stage 3 — Final Delete Confirmation")

		if deletionChoice is not "刪除來源相簿" then
			return
		end if


		-- --------------------------------------------------------
		-- DELETE SOURCE ALBUM CONTAINERS ONLY
		-- --------------------------------------------------------

		set deletedCount to 0

		repeat with sourceAlbum in refreshedSources
			delete sourceAlbum
			set deletedCount to deletedCount + 1
		end repeat

		delay 2


		-- --------------------------------------------------------
		-- FINAL VERIFICATION
		-- --------------------------------------------------------

		set finalAlbums to every album whose name is targetAlbumTitle
		set finalAlbumCount to count of finalAlbums

		if finalAlbumCount is 1 then
			set finalAlbum to item 1 of finalAlbums
			set finalAlbumID to id of finalAlbum
			set finalMediaCount to count of media items of finalAlbum

			if finalAlbumID is masterAlbumID and ¬
				finalMediaCount is uniqueCountBefore then

				display dialog ¬
					"SUCCESS — full three-stage operation verified." & return & return & ¬
					"Exact title: " & targetAlbumTitle & return & ¬
					"Deleted source albums: " & deletedCount & return & ¬
					"Albums remaining: 1" & return & ¬
					"Final master media count: " & finalMediaCount & return & return & ¬
					"No media items were deleted by this script." ¬
					buttons {"OK"} default button "OK" ¬
					with icon note ¬
					with title "REPORT-07 Complete"

			else
				display dialog ¬
					"WARNING — delete commands completed, but final verification failed." & return & return & ¬
					"Albums remaining: " & finalAlbumCount & return & ¬
					"Final media count: " & finalMediaCount & return & return & ¬
					"Use Edit > Undo Delete Album immediately if the result looks wrong." ¬
					buttons {"OK"} default button "OK" ¬
					with icon stop ¬
					with title "Final Verification Failed"
			end if

		else
			display dialog ¬
				"WARNING — delete commands completed, but the final album count is unexpected." & return & return & ¬
				"Expected remaining albums: 1" & return & ¬
				"Observed remaining albums: " & finalAlbumCount & return & return & ¬
				"Use Edit > Undo Delete Album immediately if the result looks wrong." ¬
				buttons {"OK"} default button "OK" ¬
				with icon stop ¬
				with title "Final Verification Failed"
		end if

	end timeout
end tell
