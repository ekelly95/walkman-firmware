# font-test

Shows which screens use which firmware font: Comic Sans Bold replaces ASCII in font16 (16x16)
and Consolas replaces it in font12 (12x12). The sheets are generated from Windows' fonts, so they
are not committed; recreate them with:

```
nwe39x fonts from-ttf C:/Windows/Fonts/comicbd.ttf mods/font-test/fonts/font16_comic_bold.png --font 16 --size 14
nwe39x fonts from-ttf C:/Windows/Fonts/consola.ttf mods/font-test/fonts/font12_consolas.png --font 12 --size 11
nwe39x build --mod mods/cat-lovers --fonts mods/font-test/fonts
```
