# volume-limit

Two code patches, verified on a player (1.10: the volume goes to 30 straight away) that make the firmware behave as it
does when its region/limit byte is non-zero: no clamp to volume 17 at boot, and the "may the
volume go above 17" check always says yes. Everything else (AVLS setting, the 30-step scale, the
EQ headroom limiter) is untouched. Background and addresses: NOTES.md, "Volume limit".

```
nwe39x build --mod mods/volume-limit -o out/volume-limit --version 1.12
nwe39x flash --updater out/volume-limit
nwe39x diff out/volume-limit/Data/Device/RKNANOFW.IMG
```

What to check on the player: that volume above 17 is reachable straight after power-on with no
"Check the volume level" prompt, and whether anything still pulls the volume down after a long
listening session. If it does, enable the commented section 34 line in `patches.tsv` for the next
build. Loud is loud: the limit exists for a reason, so mind your ears.
