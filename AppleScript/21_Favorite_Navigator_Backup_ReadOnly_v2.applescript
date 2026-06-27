-- ============================================================================
-- 21 Favorite Navigator -- Backup Photos Library (Read-Only) -- v2
-- ============================================================================
--
-- Open the Backup Photos Library in Photos before running this script.
--
-- This script does not change Favorite, Hidden, captions, keywords, albums,
-- folders, dates, or media. It only asks Photos to spotlight one matched item.
-- The only local write is a small progress file:
-- ~/Library/Caches/PhotosFavoriteNavigator/progress.txt
--
-- v2 deliberately uses only positional lists, not AppleScript record literals
-- or top-level property declarations, to avoid the compile failure in v1.
-- ============================================================================

on run
	set reviewTargets to my makeReviewTargets()
	set totalCount to count of reviewTargets
	set currentIndex to my readProgressIndex(totalCount)
	set targetSummary to my targetSummaryForIndex(currentIndex, reviewTargets)
	
	set actionChoices to {"Spotlight current record", "Mark current reviewed; spotlight next", "Open a specific record", "Reset progress to record 1", "Quit"}
	set promptText to "Open the Backup Photos Library before using this navigator." & return & return & "Current review position: " & currentIndex & " of " & totalCount & return & targetSummary & return & return & "This script never changes Photos metadata."
	set chosenAction to choose from list actionChoices with prompt promptText with title "21 Favorite Navigator - Backup" default items {"Spotlight current record"} OK button name "Continue" cancel button name "Quit"
	
	if chosenAction is false then return
	set selectedAction to item 1 of chosenAction
	
	if selectedAction is "Quit" then return
	
	if selectedAction is "Reset progress to record 1" then
		my writeProgressIndex(1)
		display dialog "Progress reset. Record 1 is ready." buttons {"OK"} default button "OK" with title "21 Favorite Navigator"
		return
	end if
	
	if selectedAction is "Open a specific record" then
		set recordChoices to my recordChoiceList(reviewTargets)
		set selectedRecordChoice to choose from list recordChoices with prompt "Choose one of the 21 Favorite differences to spotlight in the currently open Backup Photos Library." with title "Choose Favorite Difference" OK button name "Spotlight" cancel button name "Cancel"
		if selectedRecordChoice is false then return
		
		set selectedText to item 1 of selectedRecordChoice
		set targetIndex to my indexFromChoice(selectedText)
		if targetIndex is 0 then
			display dialog "STOPPED - unable to determine the selected record number." buttons {"OK"} default button "OK" with icon stop
			return
		end if
		
		my spotlightTargetAtIndex(targetIndex, totalCount, reviewTargets)
		return
	end if
	
	if selectedAction is "Spotlight current record" then
		my spotlightTargetAtIndex(currentIndex, totalCount, reviewTargets)
		return
	end if
	
	if selectedAction is "Mark current reviewed; spotlight next" then
		if currentIndex is greater than or equal to totalCount then
			my writeProgressIndex(totalCount)
			display dialog "All 21 records are already at the final position." & return & return & "Use Open a specific record to revisit any item, or Reset progress to record 1 to start again." buttons {"OK"} default button "OK" with icon note with title "21 Favorite Navigator"
			return
		end if
		
		set nextIndex to currentIndex + 1
		my writeProgressIndex(nextIndex)
		my spotlightTargetAtIndex(nextIndex, totalCount, reviewTargets)
		return
	end if
end run

on makeReviewTargets()
	-- Each row is: filename, year, month, day, hour, minute, second,
	--              Backup Favorite, Current Favorite.
	set targets to {}
	set end of targets to {"8188525167230255886.mp4", 2022, 5, 22, 9, 43, 18, false, true}
	set end of targets to {"IMG_0050.HEIC", 2020, 10, 16, 7, 46, 29, true, false}
	set end of targets to {"IMG_0120.JPG", 2018, 1, 11, 20, 25, 7, false, true}
	set end of targets to {"IMG_0164.PNG", 2120, 11, 28, 13, 18, 0, false, true}
	set end of targets to {"IMG_0165.PNG", 2120, 11, 28, 13, 19, 0, false, true}
	set end of targets to {"IMG_0166.PNG", 2120, 11, 28, 13, 19, 0, false, true}
	set end of targets to {"IMG_0167.PNG", 2120, 11, 28, 13, 19, 0, false, true}
	set end of targets to {"IMG_0231.JPG", 2022, 1, 14, 21, 22, 59, false, true}
	set end of targets to {"IMG_0234.JPG", 2022, 1, 15, 9, 32, 32, false, true}
	set end of targets to {"IMG_0235.JPG", 2022, 1, 15, 9, 32, 36, false, true}
	set end of targets to {"IMG_0334.MOV", 2020, 5, 9, 21, 7, 13, false, true}
	set end of targets to {"IMG_1391.MOV", 2025, 3, 17, 22, 41, 31, false, true}
	set end of targets to {"IMG_1392.MOV", 2025, 3, 17, 22, 41, 45, false, true}
	set end of targets to {"IMG_1637.PNG", 2025, 3, 20, 9, 49, 43, true, false}
	set end of targets to {"IMG_1638.PNG", 2025, 3, 20, 9, 49, 56, true, false}
	set end of targets to {"IMG_3704.MOV", 2025, 2, 8, 11, 29, 36, true, false}
	set end of targets to {"IMG_4980.MOV", 2022, 6, 30, 10, 43, 45, true, false}
	set end of targets to {"IMG_5796.JPG", 2024, 6, 14, 21, 24, 0, false, true}
	set end of targets to {"IMG_8638.jpeg", 2024, 6, 20, 20, 59, 24, false, true}
	set end of targets to {"ImageDrain-20241124T220241.356Z.jpeg", 2024, 11, 25, 6, 2, 41, false, true}
	set end of targets to {"tmp_v4738292322033630852.mp4", 2019, 11, 27, 23, 23, 10, false, true}
	return targets
end makeReviewTargets

on spotlightTargetAtIndex(targetIndex, totalCount, reviewTargets)
	set targetRecord to item targetIndex of reviewTargets
	set targetFilename to item 1 of targetRecord
	set dateText to my formattedDate(targetRecord)
	set exactMatchCount to 0
	set filenameCandidateCount to 0
	set spotlightErrorMessage to ""
	set spotlightErrorNumber to 0
	
	tell application "Photos"
		activate
		set filenameCandidates to every media item whose filename is targetFilename
		set filenameCandidateCount to count of filenameCandidates
		set exactMatches to {}
		
		repeat with candidateRef in filenameCandidates
			set candidateItem to contents of candidateRef
			try
				set candidateDate to date of candidateItem
				if my dateMatchesTarget(candidateDate, targetRecord) then set end of exactMatches to candidateItem
			end try
		end repeat
		
		set exactMatchCount to count of exactMatches
		
		if exactMatchCount is 1 then
			set matchedItem to item 1 of exactMatches
			try
				spotlight matchedItem
			on error errorMessage number errorNumber
				set spotlightErrorMessage to errorMessage
				set spotlightErrorNumber to errorNumber
			end try
		end if
	end tell
	
	if exactMatchCount is 0 then
		display dialog "STOPPED - no exact Backup-library media item was found." & return & return & "Record " & targetIndex & " of " & totalCount & return & "Original Filename: " & targetFilename & return & "Date: " & dateText & return & return & "Filename candidates found before date filtering: " & filenameCandidateCount & return & return & "Nothing in Photos was changed. The review position was not advanced." buttons {"OK"} default button "OK" with icon stop with title "Favorite Navigator - No Exact Match"
		return
	end if
	
	if exactMatchCount is not 1 then
		display dialog "STOPPED - more than one Backup-library media item matched the same filename and full date." & return & return & "Record " & targetIndex & " of " & totalCount & return & "Original Filename: " & targetFilename & return & "Date: " & dateText & return & "Exact matches: " & exactMatchCount & return & return & "Nothing in Photos was changed. Do not guess which item is correct." buttons {"OK"} default button "OK" with icon stop with title "Favorite Navigator - Ambiguous Match"
		return
	end if
	
	if spotlightErrorNumber is not 0 then
		display dialog "STOPPED - the exact item was found, but Photos rejected the spotlight command." & return & return & "Record " & targetIndex & " of " & totalCount & return & "Original Filename: " & targetFilename & return & "Date: " & dateText & return & return & "Error " & spotlightErrorNumber & ": " & spotlightErrorMessage & return & return & "Nothing in Photos was changed." buttons {"OK"} default button "OK" with icon stop with title "Favorite Navigator - Spotlight Failed"
		return
	end if
	
	display notification "Record " & targetIndex & " of " & totalCount & " highlighted in Photos." with title "21 Favorite Navigator" subtitle targetFilename
end spotlightTargetAtIndex

on dateMatchesTarget(candidateDate, targetRecord)
	try
		set expectedYear to item 2 of targetRecord
		set expectedMonth to item 3 of targetRecord
		set expectedDay to item 4 of targetRecord
		set expectedHour to item 5 of targetRecord
		set expectedMinute to item 6 of targetRecord
		set expectedSecond to item 7 of targetRecord
		set expectedSecondsSinceMidnight to (expectedHour * 3600) + (expectedMinute * 60) + expectedSecond
		
		if ((year of candidateDate) as integer) is not expectedYear then return false
		if ((month of candidateDate) as integer) is not expectedMonth then return false
		if ((day of candidateDate) as integer) is not expectedDay then return false
		if ((time of candidateDate) as integer) is not expectedSecondsSinceMidnight then return false
		return true
	on error
		return false
	end try
end dateMatchesTarget

on formattedDate(targetRecord)
	set yyyy to item 2 of targetRecord as text
	set mm to my padTwoDigits(item 3 of targetRecord)
	set dd to my padTwoDigits(item 4 of targetRecord)
	set hh to my padTwoDigits(item 5 of targetRecord)
	set mi to my padTwoDigits(item 6 of targetRecord)
	set ss to my padTwoDigits(item 7 of targetRecord)
	return yyyy & "-" & mm & "-" & dd & " " & hh & ":" & mi & ":" & ss
end formattedDate

on targetSummaryForIndex(targetIndex, reviewTargets)
	set targetRecord to item targetIndex of reviewTargets
	set targetFilename to item 1 of targetRecord
	set backupFavorite to item 8 of targetRecord
	set currentFavorite to item 9 of targetRecord
	return "Original Filename: " & targetFilename & return & "Date: " & my formattedDate(targetRecord) & return & "Backup Favorite: " & my booleanText(backupFavorite) & return & "Current Favorite: " & my booleanText(currentFavorite)
end targetSummaryForIndex

on recordChoiceList(reviewTargets)
	set choiceList to {}
	set totalCount to count of reviewTargets
	repeat with targetIndex from 1 to totalCount
		set targetRecord to item targetIndex of reviewTargets
		set targetFilename to item 1 of targetRecord
		set backupFavorite to item 8 of targetRecord
		set currentFavorite to item 9 of targetRecord
		set choiceText to targetIndex & ". " & targetFilename & " | " & my formattedDate(targetRecord) & " | Backup " & my booleanText(backupFavorite) & " -> Current " & my booleanText(currentFavorite)
		set end of choiceList to choiceText
	end repeat
	return choiceList
end recordChoiceList

on indexFromChoice(choiceText)
	set oldDelimiters to AppleScript's text item delimiters
	try
		set AppleScript's text item delimiters to ". "
		set indexText to text item 1 of choiceText
		set AppleScript's text item delimiters to oldDelimiters
		return indexText as integer
	on error
		set AppleScript's text item delimiters to oldDelimiters
		return 0
	end try
end indexFromChoice

on booleanText(booleanValue)
	if booleanValue then return "True"
	return "False"
end booleanText

on padTwoDigits(numberValue)
	set textValue to numberValue as text
	if (count of characters of textValue) is 1 then return "0" & textValue
	return textValue
end padTwoDigits

on navigatorStateDirectory()
	set homePath to POSIX path of (path to home folder)
	return homePath & "Library/Caches/PhotosFavoriteNavigator"
end navigatorStateDirectory

on progressFilePath()
	return my navigatorStateDirectory() & "/progress.txt"
end progressFilePath

on readProgressIndex(totalCount)
	set statePath to my progressFilePath()
	try
		set rawValue to do shell script "/bin/cat " & quoted form of statePath
		set storedIndex to rawValue as integer
		if storedIndex < 1 then return 1
		if storedIndex > totalCount then return totalCount
		return storedIndex
	on error
		return 1
	end try
end readProgressIndex

on writeProgressIndex(targetIndex)
	set stateDirectory to my navigatorStateDirectory()
	set statePath to my progressFilePath()
	do shell script "/bin/mkdir -p " & quoted form of stateDirectory
	do shell script "/usr/bin/printf %s " & quoted form of (targetIndex as text) & " > " & quoted form of statePath
end writeProgressIndex
