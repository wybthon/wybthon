# Deployment

Wybthon apps run entirely in the browser, so deployment is just *static hosting*. There is no Python server, no Node build step, and nothing to keep online beyond the HTML, JavaScript, and Python files you serve.

## Checklist

Before you ship:

- Serve the HTML entry point (typically `index.html`) plus the Pyodide runtime and your application files.
- Configure your host to serve `.py` files with the `text/x-python` content type — most static hosts do this automatically, but a few default to `text/plain`.
- Set [`Cross-Origin-Opener-Policy`](https://developer.mozilla.org/docs/Web/HTTP/Headers/Cross-Origin-Opener-Policy) and [`Cross-Origin-Embedder-Policy`](https://developer.mozilla.org/docs/Web/HTTP/Headers/Cross-Origin-Embedder-Policy) headers if you plan to use APIs that require cross-origin isolation (`SharedArrayBuffer`, threaded WebAssembly, etc.).
- Decide whether to load Pyodide from the official CDN (default, easiest) or to vendor it alongside your app (better caching control, supports offline-first installs).
- Enable long-cache headers for the Pyodide assets and add a content hash to your own assets so users always pick up your latest build.

## GitHub Pages

GitHub Pages serves any directory you push to the `gh-pages` branch (or to `/docs` on `main`). The simplest deployment is to copy your built site into one of those locations and push.

A minimal GitHub Actions workflow that publishes the `examples/demo/` directory looks like this:

```yaml
name: Deploy Wybthon demo

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
          path: examples/demo
      - id: deployment
        uses: actions/deploy-pages@v4
```

Use `actions/upload-pages-artifact` with the directory that contains your `index.html` (or `app/` directory) and Pages will serve it on `https://<user>.github.io/<repo>/`.

## Netlify

Netlify treats your repository as a static site by default. Create `netlify.toml` at the repo root:

```toml
[build]
  command = ""           # nothing to build
  publish = "examples/demo"

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

Push to your default branch and Netlify will auto-deploy.

## Vercel

Vercel works similarly — add a `vercel.json` at the repo root that points at your output directory:

```json
{
  "outputDirectory": "examples/demo",
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

The `rewrites` rule serves `index.html` for unknown paths, which lets the [router](../concepts/router.md) handle client-side navigation.

## Production tuning

- **Pre-compress assets.** Pre-build `.gz` and `.br` versions of `index.html` and your application files; most CDNs serve them automatically.
- **Pin Pyodide's version.** Wybthon does not ship Pyodide; reference the version you tested against from a CDN or self-host so users get the same runtime.
- **Use `set_dev_mode(False)`** (from `wybthon._warnings`) at startup in production builds to silence development warnings and skip optional bookkeeping.

## Next steps

- Read the [Pyodide guide](pyodide.md) for runtime considerations.
- Browse the [Performance guide](performance.md) for micro-optimizations.
