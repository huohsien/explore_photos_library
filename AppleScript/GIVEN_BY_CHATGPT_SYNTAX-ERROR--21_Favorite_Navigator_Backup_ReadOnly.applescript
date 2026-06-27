-- ============================================================================
-- 21 Favorite Navigator — Backup Photos Library (Read-Only)
-- ============================================================================
-- Purpose
--   Navigate one-by-one through the 21 assets whose Favorite state differed
--   between the 2025-03-17 Backup library and the Current Default library.
--
-- Before each run
--   1. Open the Backup Photos Library in Photos.
--   2. Wait until Photos finishes opening that library.
--   3. Run this script from Script Editor.
--
-- Matching rule
--   Exact Original Filename + full Date to whole seconds.
--   If zero or more than one Photos media item matches, the script stops safely
--   and does not advance its review position.
--
-- What this script changes
--   - Photos: nothing. It only activates Photos and uses spotlight to navigate.
--   - Local state only: one tiny progress file in ~/Library/Caches/
--     PhotosFavoriteNavigator/progress.txt, so that separate runs remember
--     which item is currently under review. "Reset to item 1" rewrites it.
--
-- It does NOT change Favorite, Hidden, metadata, albums, folders, or media.
-- ============================================================================

property reviewTargets : {¬
    {originalFilename:"8188525167230255886.mp4", targetYear:2022, targetMonth:5, targetDay:22, targetHour:9, targetMinute:43, targetSecond:18, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_0050.HEIC", targetYear:2020, targetMonth:10, targetDay:16, targetHour:7, targetMinute:46, targetSecond:29, backupFavorite:true, currentFavorite:false}, ¬
    {originalFilename:"IMG_0120.JPG", targetYear:2018, targetMonth:1, targetDay:11, targetHour:20, targetMinute:25, targetSecond:7, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_0164.PNG", targetYear:2120, targetMonth:11, targetDay:28, targetHour:13, targetMinute:18, targetSecond:0, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_0165.PNG", targetYear:2120, targetMonth:11, targetDay:28, targetHour:13, targetMinute:19, targetSecond:0, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_0166.PNG", targetYear:2120, targetMonth:11, targetDay:28, targetHour:13, targetMinute:19, targetSecond:0, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_0167.PNG", targetYear:2120, targetMonth:11, targetDay:28, targetHour:13, targetMinute:19, targetSecond:0, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_0231.JPG", targetYear:2022, targetMonth:1, targetDay:14, targetHour:21, targetMinute:22, targetSecond:59, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_0234.JPG", targetYear:2022, targetMonth:1, targetDay:15, targetHour:9, targetMinute:32, targetSecond:32, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_0235.JPG", targetYear:2022, targetMonth:1, targetDay:15, targetHour:9, targetMinute:32, targetSecond:36, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_0334.MOV", targetYear:2020, targetMonth:5, targetDay:9, targetHour:21, targetMinute:7, targetSecond:13, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_1391.MOV", targetYear:2025, targetMonth:3, targetDay:17, targetHour:22, targetMinute:41, targetSecond:31, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_1392.MOV", targetYear:2025, targetMonth:3, targetDay:17, targetHour:22, targetMinute:41, targetSecond:45, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_1637.PNG", targetYear:2025, targetMonth:3, targetDay:20, targetHour:9, targetMinute:49, targetSecond:43, backupFavorite:true, currentFavorite:false}, ¬
    {originalFilename:"IMG_1638.PNG", targetYear:2025, targetMonth:3, targetDay:20, targetHour:9, targetMinute:49, targetSecond:56, backupFavorite:true, currentFavorite:false}, ¬
    {originalFilename:"IMG_3704.MOV", targetYear:2025, targetMonth:2, targetDay:8, targetHour:11, targetMinute:29, targetSecond:36, backupFavorite:true, currentFavorite:false}, ¬
    {originalFilename:"IMG_4980.MOV", targetYear:2022, targetMonth:6, targetDay:30, targetHour:10, targetMinute:43, targetSecond:45, backupFavorite:true, currentFavorite:false}, ¬
    {originalFilename:"IMG_5796.JPG", targetYear:2024, targetMonth:6, targetDay:14, targetHour:21, targetMinute:24, targetSecond:0, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"IMG_8638.jpeg", targetYear:2024, targetMonth:6, targetDay:20, targetHour:20, targetMinute:59, targetSecond:24, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"ImageDrain-20241124T220241.356Z.jpeg", targetYear:2024, targetMonth:11, targetDay:25, targetHour:6, targetMinute:2, targetSecond:41, backupFavorite:false, currentFavorite:true}, ¬
    {originalFilename:"tmp_v4738292322033630852.mp4", targetYear:2019, targetMonth:11, targetDay:27, targetHour:23, targetMinute:23, targetSecond:10, backupFavorite:false, currentFavorite:true} ¬
}

on run
    set totalCount to count of my reviewTargets
    set currentIndex to my readProgressIndex(totalCount)
    set targetSummary to my targetSummaryForIndex(currentIndex, totalCount)

    set actionChoices to {¬
        "Spotlight current record", ¬
        "Mark current reviewed; spotlight next", ¬
        "Open a specific record…", ¬
        "Reset progress to record 1", ¬
        "Quit" ¬
    }

    set promptText to "Open the Backup Photos Library before using this navigator." & return & return & ¬
        "Current review position: " & currentIndex & " of " & totalCount & return & ¬
        targetSummary & return & return & ¬
        "This script never changes Photos metadata."

    set chosenAction to choose from list actionChoices with prompt promptText with title "21 Favorite Navigator — Backup" default items {"Spotlight current record"} OK button name "Continue" cancel button name "Quit"

    if chosenAction is false then return

    set selectedAction to item 1 of chosenAction

    if selectedAction is "Quit" then return

    if selectedAction is "Reset progress to record 1" then
        my writeProgressIndex(1)
        display notification "Progress reset. Record 1 is ready." with title "21 Favorite Navigator"
        return
    end if

    if selectedAction is "Open a specific record…" then
        set recordChoices to my recordChoiceList()
        set selectedRecordChoice to choose from list recordChoices with prompt "Choose one of the 21 Favorite differences to spotlight in the currently open Backup Photos Library." with title "Choose Favorite Difference" OK button name "Spotlight" cancel button name "Cancel"

        if selectedRecordChoice is false then return

        set selectedText to item 1 of selectedRecordChoice
        set targetIndex to my indexFromChoice(selectedText)
        if targetIndex is 0 then
            display dialog "STOPPED — unable to determine the selected record number." buttons {"OK"} default button "OK" with icon stop
            return
        end if

        my spotlightTargetAtIndex(targetIndex, totalCount)
        return
    end if

    if selectedAction is "Spotlight current record" then
        my spotlightTargetAtIndex(currentIndex, totalCount)
        return
    end if

    if selectedAction is "Mark current reviewed; spotlight next" then
        if currentIndex is greater than or equal to totalCount then
            my writeProgressIndex(totalCount)
            display dialog "All 21 records are already at the final position." & return & return & ¬
                "Use ‘Open a specific record…’ to revisit any item, or ‘Reset progress to record 1’ to start again." buttons {"OK"} default button "OK" with icon note with title "21 Favorite Navigator"
            return
        end if

        set nextIndex to currentIndex + 1
        my writeProgressIndex(nextIndex)
        my spotlightTargetAtIndex(nextIndex, totalCount)
        return
    end if
end run

on spotlightTargetAtIndex(targetIndex, totalCount)
    set targetRecord to item targetIndex of my reviewTargets
    set targetFilename to originalFilename of targetRecord
    set dateText to my formattedDate(targetRecord)

    tell application "Photos"
        activate

        -- First filter by the exact filename. Date filtering is then performed
        -- in AppleScript component-by-component to whole seconds.
        set filenameCandidates to every media item whose filename is targetFilename
        set exactMatches to {}

        repeat with candidateRef in filenameCandidates
            set candidateItem to contents of candidateRef
            try
                set candidateDate to date of candidateItem
                if my dateMatchesTarget(candidateDate, targetRecord) then
                    set end of exactMatches to candidateItem
                end if
            end try
        end repeat

        set exactMatchCount to count of exactMatches

        if exactMatchCount is 0 then
            display dialog "STOPPED — no exact Backup-library media item was found." & return & return & ¬
                "Record " & targetIndex & " of " & totalCount & return & ¬
                "Original Filename: " & targetFilename & return & ¬
                "Date: " & dateText & return & return & ¬
                "Filename candidates found before date filtering: " & (count of filenameCandidates) & return & return & ¬
                "Nothing in Photos was changed. The review position was not advanced." buttons {"OK"} default button "OK" with icon stop with title "Favorite Navigator — No Exact Match"
            return
        end if

        if exactMatchCount is not 1 then
            display dialog "STOPPED — more than one Backup-library media item matched the same filename and full date." & return & return & ¬
                "Record " & targetIndex & " of " & totalCount & return & ¬
                "Original Filename: " & targetFilename & return & ¬
                "Date: " & dateText & return & ¬
                "Exact matches: " & exactMatchCount & return & return & ¬
                "Nothing in Photos was changed. Do not guess which item is correct." buttons {"OK"} default button "OK" with icon stop with title "Favorite Navigator — Ambiguous Match"
            return
        end if

        set matchedItem to item 1 of exactMatches

        try
            spotlight matchedItem
        on error errorMessage number errorNumber
            display dialog "STOPPED — the exact item was found, but Photos rejected the spotlight command." & return & return & ¬
                "Record " & targetIndex & " of " & totalCount & return & ¬
                "Original Filename: " & targetFilename & return & ¬
                "Date: " & dateText & return & return & ¬
                "Error " & errorNumber & ": " & errorMessage & return & return & ¬
                "Nothing in Photos was changed." buttons {"OK"} default button "OK" with icon stop with title "Favorite Navigator — Spotlight Failed"
            return
        end try
    end tell

    -- The script returns immediately after this notification so that you can
    -- inspect the highlighted item and, if you decide to, change its Favorite
    -- state manually in Photos. Run the script again only after you are done.
    display notification "Record " & targetIndex & " of " & totalCount & " highlighted in Photos." with title "21 Favorite Navigator" subtitle targetFilename
end spotlightTargetAtIndex

on dateMatchesTarget(candidateDate, targetRecord)
    try
        set expectedSecondsSinceMidnight to ((targetHour of targetRecord) * 3600) + ((targetMinute of targetRecord) * 60) + (targetSecond of targetRecord)

        if (year of candidateDate as integer) is not (targetYear of targetRecord) then return false
        if (month of candidateDate as integer) is not (targetMonth of targetRecord) then return false
        if (day of candidateDate as integer) is not (targetDay of targetRecord) then return false
        if (time of candidateDate as integer) is not expectedSecondsSinceMidnight then return false

        return true
    on error
        return false
    end try
end dateMatchesTarget

on formattedDate(targetRecord)
    set yyyy to targetYear of targetRecord as text
    set mm to my padTwoDigits(targetMonth of targetRecord)
    set dd to my padTwoDigits(targetDay of targetRecord)
    set hh to my padTwoDigits(targetHour of targetRecord)
    set mi to my padTwoDigits(targetMinute of targetRecord)
    set ss to my padTwoDigits(targetSecond of targetRecord)
    return yyyy & "-" & mm & "-" & dd & " " & hh & ":" & mi & ":" & ss
end formattedDate

on targetSummaryForIndex(targetIndex, totalCount)
    set targetRecord to item targetIndex of my reviewTargets
    return "Original Filename: " & (originalFilename of targetRecord) & return & ¬
        "Date: " & my formattedDate(targetRecord) & return & ¬
        "Backup Favorite: " & my booleanText(backupFavorite of targetRecord) & return & ¬
        "Current Favorite: " & my booleanText(currentFavorite of targetRecord)
end targetSummaryForIndex

on recordChoiceList()
    set choiceList to {}
    set totalCount to count of my reviewTargets

    repeat with targetIndex from 1 to totalCount
        set targetRecord to item targetIndex of my reviewTargets
        set choiceText to targetIndex & ". " & (originalFilename of targetRecord) & " | " & my formattedDate(targetRecord) & " | Backup " & my booleanText(backupFavorite of targetRecord) & " → Current " & my booleanText(currentFavorite of targetRecord)
        set end of choiceList to choiceText
    end repeat

    return choiceList
end recordChoiceList

on indexFromChoice(choiceText)
    try
        set oldDelimiters to AppleScript's text item delimiters
        set AppleScript's text item delimiters to ". "
        set indexText to text item 1 of choiceText
        set AppleScript's text item delimiters to oldDelimiters
        return indexText as integer
    on error
        try
            set AppleScript's text item delimiters to oldDelimiters
        end try
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
    return (POSIX path of (path to caches folder from user domain)) & "PhotosFavoriteNavigator"
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
