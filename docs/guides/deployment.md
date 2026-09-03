# Deployment

Wybthon apps run entirely in the browser, so deployment is *static hosting*. There's no Python server, no Node build step, and nothing to keep online beyond the HTML, JavaScript, and Python files you serve.

## Checklist

Before you ship:

- Serve the HTML entry point (typically `index.html`) plus your `bootstrap.js` and application files. Pyodide itself can come from the official CDN or be vendored alongside your app.
- Configure your host to serve `.py` files with the `text/x-python` content type. Most static hosts do this automatically, but a few default to `text/plain`.
- Set [`Cross-Origin-Opener-Policy`](https://developer.mozilla.org/docs/Web/HTTP/Headers/Cross-Origin-Opener-Policy) and [`Cross-Origin-Embedder-Policy`](https://developer.mozilla.org/docs/Web/HTTP/Headers/Cross-Origin-Embedder-Policy) headers if you plan to use APIs that require cross-origin isolation (`SharedArrayBuffer`, threaded WebAssembly, and so on).
- Decide whether to load Pyodide from the CDN (default, easiest) or to vendor it (better caching control, supports offline-first installs).
- Enable long-cache headers for the Pyodide assets and add a content hash or version query to your own assets so users always pick up your latest build.
- Add a single-page app fallback that serves `index.html` for unknown paths, so deep links reach the [router](../concepts/router.md).

## Turning off dev mode

Wybthon's dev-mode diagnostics (top-level-read warnings, `WriteInScopeError`, tracebacks in error logs) are on by default. Turn them off at startup in production:

```python
from wybthon import render, set_dev_mode

set_dev_mode(False)
render(App(), "#app")
```

A simple way to keep one entry point for both environments is to read a flag from the page:

```python
from js import window

from wybthon import set_dev_mode

set_dev_mode(bool(getattr(window, "WYB_DEV", False)))
```

## GitHub Pages

GitHub Pages serves any directory you push to the `gh-pages` branch (or to `/docs` on `main`). The simplest deployment is to publish the repository root, where `index.html` lives in apps like the [demo-template](https://github.com/wybthon/demo-template).

A minimal GitHub Actions workflow:

```yaml
name: Deploy Wybthon app

on:
  push:
    branches: [main]

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: .
      - id: deployment
        uses: actions/deploy-pages@v4
```

Point `actions/upload-pages-artifact` at the directory that contains your `index.html`, and Pages serves it on `https://<user>.github.io/<repo>/`. Because the app lives under `/<repo>/`, pass `base_path="/<repo>"` to [`Router`][wybthon.Router] so links and matching account for the prefix.

## Netlify

Netlify treats your repository as a static site by default. Create `netlify.toml` at the repo root:

```toml
[build]
  command = ""           # nothing to build
  publish = "."

[[headers]]
  for = "/*"
  [headers.values]
    Cache-Control = "public, max-age=300"

[[headers]]
  for = "/*.py"
  [headers.values]
    Content-Type = "text/x-python"
    Cache-Control = "public, max-age=300"

# Single-page app fallback so the router can handle deep links.
[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

Push to your default branch and Netlify auto-deploys.

## Vercel

Vercel works similarly. Add a `vercel.json` at the repo root that points at your output directory:

```json
{
  "outputDirectory": ".",
  "headers": [
    {
      "source": "/(.*).py",
      "headers": [{ "key": "Content-Type", "value": "text/x-python" }]
    }
  ],
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

The `rewrites` rule serves `index.html` for unknown paths, which lets the router handle client-side navigation.

## Production tuning

- **Pre-compress assets.** Pre-build `.gz` and `.br` versions of `index.html` and your application files; most CDNs serve them automatically.
- **Pin Pyodide's version.** Wybthon doesn't ship Pyodide; reference the version you tested against (the framework's own suite runs on 314.0.6) from a CDN or self-host it so users get the same runtime.
- **Pin Wybthon too.** `micropip.install("wybthon==0.30.0")` keeps production on the release you tested.
- **Call `set_dev_mode(False)`.** It silences warnings and skips optional bookkeeping.
- **Split large pages with `lazy`.** Route pages loaded through [`lazy`][wybthon.lazy] keep the initial import (and the initial Pyodide filesystem copy) small.

## Next steps

- Read the [Pyodide guide](pyodide.md) for runtime considerations.
- Browse the [Performance guide](performance.md) for authoring tips that keep updates cheap.
