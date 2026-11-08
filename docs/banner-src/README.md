# Banner source

`docs/banner.png` (1280×640) is `banner.html` rendered in headless Chrome at 2× and
downscaled. It embeds `../screenshots/desktop-page.png`. To regenerate after a new
screenshot: open `banner.html` at a 1280×640 viewport and capture, or run the CDP
harness in `web/dev/cdp.mjs` with that viewport (`Emulation.setDeviceMetricsOverride`
1280×640, scale 2), then `sips -Z 1280`.
