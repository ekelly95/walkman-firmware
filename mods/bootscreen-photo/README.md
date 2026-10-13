# bootscreen-photo

Boot (044) and power-off (083) screens made from photos with `nwe39x bootscreen`, captioned in
Terminus 12 to match the menu font: a green aurora with "Hello Again", and a dark green light trail
with "See You Later". The photos are from Unsplash (free under the Unsplash License) and are not
committed; download them and regenerate:

- Boot: [Green northern lights](https://unsplash.com/photos/green-northern-lights-xGltqb1ChYw) by Jack Young
- Power off: [Green light in dark room](https://unsplash.com/photos/green-light-in-dark-room-aka-hHVgZQ8) by Alex Middleton

```
nwe39x bootscreen aurora.jpg mods/bootscreen-photo/images/044.png --caption "Hello Again" --font reference/terminus/terminus-ttf-4.49.3/TerminusTTF-Bold-4.49.3.ttf --font-size 12
nwe39x bootscreen green-light.jpg mods/bootscreen-photo/images/083.png --caption "See You Later" --focus 0.75,0.75 --zoom 1.6 --font reference/terminus/terminus-ttf-4.49.3/TerminusTTF-Bold-4.49.3.ttf --font-size 12
nwe39x build --mod mods/my-walkman -o out/my-walkman
```

Any photo works: `--focus` picks the part to keep (fractions across and down), `--zoom` crops
tighter, `--caption` takes lines separated by `|`, and `--preview` writes a 3x enlargement.
