# Flashing from Linux

**Untested on a player.** Windows is the tested way to install. On Linux, `flash.py` sends the same
two SCSI commands with SG_IO on the player's `/dev/sgN`. The code is checked against a real kernel
(the `sg_io_hdr` layout, and finding the device from a mount point), but no Linux machine has sent them
to a player yet. A bad install has no known recovery, so go one step at a time.

## 1. Let your user send SCSI commands to the player

Vendor commands need write access to `/dev/sgN`, which is `root:disk` by default. Give the
person at the keyboard access to this player only (Sony `054c:0b83`):

```bash
echo 'SUBSYSTEM=="scsi_generic", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0b83", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/70-nwe39x.rules
```

```bash
sudo udevadm control --reload
```

Then unplug and replug the player. If `ls /sys/block/sd*/device/scsi_generic` shows nothing,
load the sg driver with `sudo modprobe sg`.

## 2. Read-only check: `devinfo`

Plug in the player and let Dolphin mount it (on Arch/CachyOS it appears as `/run/media/$USER/WALKMAN`;
some distros use `/media/$USER/WALKMAN`), then:

```bash
uv run nwe39x devinfo
```

It should print `SONY NW-E394` (or your model), the header version and the serial, the same as on
Windows. This command only reads; it cannot change the player. If it fails, stop and keep flashing
from Windows.

## 3. Flash

Only after `devinfo` answers correctly. Start with `out/stock-restore`, the build you can least
afford to get wrong but that changes nothing:

```bash
NWE39X_LINUX_FLASH=1 uv run nwe39x flash --updater out/stock-restore
```

Every Windows check still runs first, and `flash` refuses before asking you to confirm if
`NWE39X_LINUX_FLASH=1` is missing. On Linux, `flash` then:

1. finds the player's `/dev/sgN` and its partition (say `/dev/sdb1`) while it is still mounted;
2. copies the image and syncs it;
3. **unmounts the player** with `udisksctl unmount`, so Linux can't write to the filesystem while the
   player reads the image and rewrites it. If something is using the player (a Dolphin window, a
   terminal inside it), this fails and nothing is sent: close it and run `flash` again;
4. sends START FW UPDATE to `/dev/sgN`. If the USB link drops as the player takes the command, that
   usually means it reset to install, so `flash` says so and keeps waiting. **Don't unplug it;**
5. waits for the player to leave USB and come back, and only accepts the player with the same
   serial (`devinfo`), even if Linux mounts it as `WALKMAN1` or another player is plugged in.

If it doesn't come back mounted, open it in Dolphin. If it reports the version you expected, Linux
flashing works for you.
