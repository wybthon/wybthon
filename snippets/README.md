# Snippets — tweetable Wybthon code

Bite-sized, screenshot-ready Wybthon examples designed to be posted on
X/Twitter. Each file is **self-contained**, **complete**, and small
enough to fit in one screenshot.

Every snippet has a top-of-file docstring with:

- a one-line **tweet caption** (copy/paste-ready),
- a 2-3 line note on **why it's interesting** (use for thread context),
- the actual code below it.

## Snippets

| File | What it shows | Lines |
| --- | --- | --- |
| `counter.py` | The 8-line classic. Signals + reactive holes. | ~20 |
| `stopwatch.py` | Start / stop / reset. `on_mount` + `on_cleanup`. | ~35 |
| `todo_app.py` | Add, toggle, delete. `For` + per-item reactive scopes. | ~50 |
| `live_search.py` | Filter-as-you-type with `create_memo`. | ~35 |
| `async_fetch.py` | `create_resource` + `Suspense` for loading states. | ~40 |
| `form_validation.py` | `form_state` + declarative validators. | ~50 |
| `dark_mode.py` | Reactive context with `Provider` + `use_context`. | ~50 |
| `mini_spa.py` | Client-side routing with path params + 404. | ~55 |
| `derived_state.py` | Two-way derived state (°C ↔ °F). | ~45 |
| `tic_tac_toe.py` | A complete game with win detection. | ~55 |

## How to post one

1. **Pick a snippet** that matches the angle you want to land
   (beginner-friendly → `counter`, depth → `tic_tac_toe`,
   framework-comparison → `todo_app` or `dark_mode`).
2. **Screenshot the code** in your editor with a clean theme
   (high contrast, no minimap, no breadcrumbs). Tools like
   `carbon.now.sh` or `ray.so` work too.
3. **Use the docstring tweet caption** as your post copy — or
   write your own riff on it. Drop the import-block in the
   screenshot only if it fits without shrinking the body.
4. **Link in a reply**, not the original post — Twitter throttles
   posts with outbound links. Reply with:
   `Repo: github.com/wybthon/wybthon · Docs: docs.wybthon.com`.

## Caption playbook

Strong hooks for code posts on X:

- **Comparison.** "This is what a counter looks like in
  Wybthon vs React." Show both, side-by-side.
- **Counter-intuitive claim.** "You can build a SPA without
  writing a single line of JavaScript." Then prove it.
- **Tiny scope.** "Live search in 12 lines of Python." People
  scroll-stop on small numbers.
- **One-liner question.** "What if Python ran your frontend?"
  Then attach the screenshot.

Avoid:

- Long captions. Two lines max in the post itself.
- Emojis stacked at the start of the post — looks like spam.
- Hashtags in the body. If you must, one at the very end.

## Posting cadence

- 1 snippet per day at most. Pick the strongest one each week.
- Best windows (US-centric): 9-11am ET on weekdays, or
  6-8pm ET on Sunday evenings.
- Reply-thread the rest of the family ("here's the same idea
  with X / Y / Z") to drive depth without spamming the feed.

## Mounting any snippet

These files define a component. To actually render one in a
Pyodide page:

```python
from js import document
from wybthon import h, render

render(h(Counter, {}), document.getElementById("root"))
```

See [`docs.wybthon.com/getting-started`](https://docs.wybthon.com/getting-started/)
for the full bootstrap (one HTML file + one `bootstrap.js`).
