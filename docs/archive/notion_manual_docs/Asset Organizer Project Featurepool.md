# Feature Pool

[Asset Organizer Hiatus Usage Discoveries](https://www.notion.so/Asset-Organizer-Hiatus-Usage-Discoveries-302580296de680a5bb08c389e69d0023?pvs=21)

<aside>
<img src="https://www.notion.so/icons/star_orange.svg" alt="https://www.notion.so/icons/star_orange.svg" width="40px" />

### *Priority Feature Trajectories:*

1. Asset detection system robustness
2. Project detection system robustness
3. Streamlined user-facing organization systems

<aside>
<img src="https://www.notion.so/icons/bug_gray.svg" alt="https://www.notion.so/icons/bug_gray.svg" width="40px" />

### Bugs

- Stage 8
- Stage 9
    - [x]  **Overlapping text for asset tags:** Tags shown in the library view are overlapping
    - [ ]  **9.2.2 Foreign key error for unregister root:** Cascade unregister failing with error
        - Log (legacy remove root click)
            
            Traceback (most recent call last):
            File "A:\Art\Scripts\AssetHubProject\AssetHub\src\assethub\ui\views\scan_tab.py", line 330, in _on_remove_root
            sm.unregister_root(storage_id)
            File "A:\Art\Scripts\AssetHubProject\AssetHub\src\assethub\core\storage\[roots.py](http://roots.py/)", line 209, in unregister_root
            self._conn.execute("DELETE FROM storage WHERE id = ?;", (sid,))
            sqlite3.IntegrityError: FOREIGN KEY constraint failed
            
- Stage n
- Unconfirmed
    - [ ]  **File duplication:** Something to do with the scan assets / health check separation clashing. Removing a file from tracking in the asset level view causes a missing file to duplicate itself in the detect assets UI. A checksum gate may solve this because it can identify a *moved* file rather than a deleted one.
        - *Bug catch process*
            1. Scan roots: indexed 133 files
            2. Health check: all OK
            3. Created texture asset via detect assets dialog
            4. IN FILE SYSTEM: Moved normal map of asset up one directory
            5. Run health check: one file missing
            6. Scan roots: indexed 133 files
            7. Asset tab reports one file missing from asset, targeted health check: 1 missing
            8. Detect assets: create new asset from moved normal map
    - [ ]  **Asset detection bug:** A file that was removed, scanned, and added back, and scanned to the database again does not appear in the dialog.
        - *Bug catch process*
</aside>

<aside>
<img src="https://www.notion.so/icons/plus_gray.svg" alt="https://www.notion.so/icons/plus_gray.svg" width="40px" />

### New Features

- Stage 7
    - [x]  **Storage roots nicknames: S**torage root display name in-app, does not rename folder on disk to keep no-write design principle
    **Value:** High
    **Cost:** Low
    - [x]  **Delete roots cascade:** Currently no way to delete storage roots from tracking without clearing all files from the storage
    **Value:** High
    **Cost:** Low-Medium
- Stage 8
- Stage 9
    - *High Priority*
        - [x]  **Tag Assets (User):** Implement tables for user tags on assets for sorting and filtering
        - [ ]  **Filter Rules UI: N**otion-like rules filter and sorting enhancements. Set rule blocks with dropdowns for: 
        1. Input: “file name” / “file type” / “integrity”
        2. Conditional: “contains” / “is” / “is not”
        3. Reference: null / string / int / float
    - *Medium Priority*
        - [ ]  **Add filetype attribute:** Create a file type column in file table allowing for filtering by file type
        - [ ]  **Multi-dissolve assets:** Currently only works for one asset at a time, probably because modal confirmation dialog is limited to one asset
    - *Low Priority*
        - [ ]  **Split-pane details view in library assets mode:** A details window showing a preview below the files and versions panes to view files in asset mode, less switching/searching required. Place this directly below the version and file list panes.
        - [ ]  **Reveal storage roots location in context:** Quickly open storage root location in explorer via rmb in scan tab table
- Stage n
    - *High Priority*
        - [ ]  **Scanner Project Identification:** Scan ingests project files (.mel) to mark directories as projects.
        - [ ]  **Detect Assets Project Identification:** Detect assets can mark projects on asset proposals based on name (limited to available projects, doesn’t try to suggest new)
    - *Medium Priority*
        - [ ]  **Re-Detect on File Binding:** Run file detection on an asset whenever a user manually attaches files to make another guess to what the file is.
    - *Low Priority*
        - [ ]  **Mark version as latest:** Because we allow for renaming versions, it would be helpful to indicate which is latest by default
</aside>

<aside>
<img src="https://www.notion.so/icons/swap-horizontally_gray.svg" alt="https://www.notion.so/icons/swap-horizontally_gray.svg" width="40px" />

### Adjust Features

- Stage 7
    - [x]  **Move Summary Log to MainWindow:** The summary log in the scan tab can be moved under the main tabs section as a small log area for function execution
    **Value:** High
    **Cost:** Medium
- Stage 8
    
    **Detect assets proposal dialog tweaks**
    
    - [x]  **Add multi-select for proposals:** Multi-select for asset proposals to mass activate / deactivate, rather than clicking each proposal individually and using the “select none” button.
    
    **Library tab Assets view:**
    
    - [x]  **Asset list selection bug:** Clicking an asset in the list sometimes does not update versions and files pane until you refresh the view, and even then, it sometimes still doesn’t update.
    - [x]  **Search and filter compatibility:** Search bar does not function in assets mode unless refresh button pressed. The integrity filter is also grayed out.
    - [x]  **Show hidden checkbox:** Inactive in assets mode, would be nice addition for developers
    - [x]  **Right-click context menu for assets view:** Tools for actions like “dissolve asset” to remove the asset group from the database and release associated files and the standard tools included in the file context menu like ”open asset location”
    - [x]  **Right-click context menu for files in assets view:** Take the same context menu system for files and enable it for the files list associated with an asset version.
    - [x]  **Multi-select assets for dissolve context menu action**
- Stage 9
    - *High Priority*
        - [x]  **Link file to asset:** Currently no way to add files to an asset (and version up?) after creating the asset via the detection interface.
        - [x]  **Multi-select in assets view:** Currently multi-select is not enabled for the assets view of the library tab. We need this for mass-assigning tags to assets.
        - [ ]  **Manual Binding System Apply to All Version/Files:** Files assigned to an asset that have been bound via detection should be able to be force unbound by the user. That is, there’s currently no way to unassign a file from an asset manually unless the user bound it manually.
    - *Medium Priority*
        - [ ]  **Clear UI indicator for detect asset dialog version-up:** Edits to current asset entries are not shown, needs some sort of indicator that a merge + version up is occurring rather than a new asset.
    - *Low Priority*
        - [ ]  **Disallow Context Menu Actions for Old Version/Files:** Actions like “unbind file from asset”
- Stage n
    - *High Priority*
        - [ ]  **Expand asset detection variety:** WIP, possible branch
    - *Medium Priority*
        - [ ]  **Detect assets user-editable filetype exclusion filter:** Menu to enter which file types to exclude in the asset detection (.rat / .tx)
        - [ ]  **Add non-detected supporting files to detect assets proposal:** Ability to add / remove files outside detection for asset directly within dialog. ex: add asset header image / README.txt file info associated with texture set, .mov of compiled image sequence, etc… (”supporting files”). For v0, we can suggest supporting files within the same directory as the asset files.
        - [ ]  **Expand Preview Compatibility:** Long-term goal to make more file formats preview-able
        **Value:** Medium
        **Cost:** Medium
    - *Low Priority*
        - [ ]  **Replace scan button with watchdog:** When file system updates within tracked storage roots, pulse db_update for EventHub
        **Value:** Medium (quality of life)
        **Cost:** High
</aside>

<aside>
<img src="https://www.notion.so/icons/remove_gray.svg" alt="https://www.notion.so/icons/remove_gray.svg" width="40px" />

### Remove Features

- Stage n
    - *Low Priority*
        - [ ]  **Safe unregister storage root:** Once we get to asset tracking we’ll know for sure, but it may be unnecessary once cascade remove is implemented. We’ll wait because asset tacking is still unsure
</aside>

</aside>

<aside>
<img src="https://www.notion.so/icons/sponge_gray.svg" alt="https://www.notion.so/icons/sponge_gray.svg" width="40px" />

### Code Hygiene (as needed)

- Stage 7
    - [x]  **Docstring standardization pass:** A pass to make sure that all docstrings are up to date, descriptive, and standardized.
    **Value:** Medium
    **Cost:** Medium (time)
    - [x]  **Test suite deprecation audit:** A pass to confirm the testing suite is practical. Make sure that none of them are deprecated based on our changes.
    **Value:** High
    **Cost:** Low-Medium
- Stage 9
    - [ ]  **Design Summary / Devlog:** Updates to design decisions and work completed documentation
</aside>