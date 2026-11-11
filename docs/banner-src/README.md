# Banner source

`docs/banner.png` (1280×640) is `banner.html` rendered in headless Chrome at 2× and
downscaled. It embeds `room.png`, a capture of the editor with labels off. To
regenerate:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --window-size=1280,640 --force-device-scale-factor=2 \
  --screenshot=/tmp/banner@2x.png "file://$PWD/docs/banner-src/banner.html"
sips -Z 1280 /tmp/banner@2x.png --out docs/banner.png   # then re-save without metadata
```
