### Deployment

Since Wybthon apps run fully client-side, deployment is static hosting.

Checklist:

- Serve the HTML/JS bundle (Pyodide + your app assets)
- Set correct `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` if using features that require them
- Use a CDN for Pyodide or host locally

> TODO: Provide example configurations for GitHub Pages, Netlify, and Vercel.
