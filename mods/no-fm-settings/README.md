# no-fm-settings

Drops FM Radio Settings from the Settings menu, to go with `no-fm`. The Settings menu is a tree in
the string table's record headers (see NOTES.md), so this rewrites the headers of Settings and its
neighbours in all 13 language blocks: the child list and count, the kept rows' indices, and the
sibling links around the hidden entry. The FM records stay in the table, unreachable. Regenerate
after changing the firmware version:

```
nwe39x menu settings
nwe39x menu settings-hide "FM Radio" -o mods/no-fm-settings/patches.tsv
nwe39x build --mod mods/no-fm-settings -o out/no-fm-settings
nwe39x diff out/no-fm-settings/Data/Device/RKNANOFW.IMG
```
