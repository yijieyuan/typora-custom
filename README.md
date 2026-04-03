# README

This repo contains custom Typora themes and a post-processing script to export Markdown as HTML that looks the same on webpages as in Typora.

## Custom Themes

- **academic.css** — Modified version of the public [Academic theme](https://theme.typora.io/theme/Academic/)
- **note.css** — Template used to generate articles for my website

## Custom HTML Export

1. Export HTML from Typora: **File → Export → HTML**
2. Post-process the exported HTML using one of:
   - **Option A: Right-click context menu**
     1. Edit `install-context-menu.reg` and update the path to `convert-to-note-html.py`
     2. Double-click `install-context-menu.reg` to register the menu entry
     3. Right-click the `.html` file → **Convert to Note HTML**
     4. To remove: double-click `uninstall-context-menu.reg`

     The registry entry points to the script path, so changes to `convert-to-note-html.py` take effect immediately. Only re-run the `.reg` if the script path or Python path changes.

   - **Option B: Custom export in Typora**
     1. Open **File → Preferences → Export → HTML**
     2. Under "Run custom command after export", set to: `python "path/to/convert-to-note-html.py" "${outputPath}"`
     3. Now **File → Export → HTML** will automatically post-process the output
