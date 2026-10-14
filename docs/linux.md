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

Plug in the player and let Dolphin mount it (it appears as `/media/$USER/WALKMAN`), then:

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

Every Windows check still runs first. On Linux, `flash` also syncs the image's directory entry and the
filesystem before sending START FW UPDATE. Linux may not remount the player when it restarts: if
`flash` waits, open it in Dolphin. If it reports the version you expected, Linux flashing works for you.
