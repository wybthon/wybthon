### wybthon._warnings

::: wybthon._warnings

#### What's in this module

`_warnings` is Wybthon's lightweight development-mode diagnostics
layer. It gives the framework a single place to surface actionable
warnings and error tracebacks while developing, without adding any
runtime cost or noise to production builds.

Three things live here:

- **Dev-mode toggling**: [`DEV_MODE`][wybthon._warnings.DEV_MODE]
  defaults to `True`. Call
  [`set_dev_mode(False)`][wybthon._warnings.set_dev_mode] at startup
  to silence warnings and traceback printing for production builds;
  [`is_dev_mode()`][wybthon._warnings.is_dev_mode] reports the current
  state. Both are re-exported from the top-level `wybthon` package.
- **One-shot warnings**: [`warn`][wybthon._warnings.warn] prints a
  message to `stderr` every time it's called (a no-op when dev mode is
  off), while [`warn_once`][wybthon._warnings.warn_once] deduplicates
  by a `(category, key)` pair so a recurring mistake -- like the same
  component destructuring the same prop on every render -- only ever
  logs once per process. `warn_destructured_prop` and
  `warn_each_plain_list` are the two built-in warnings that use this
  path today.
- **Error logging**: [`log_error`][wybthon._warnings.log_error] always
  prints, regardless of `DEV_MODE`, since it represents a real error
  rather than a stylistic nit; in dev mode it also prints the full
  traceback of an attached exception.

`component_name` is a small formatting helper shared by the warning
functions above to produce a readable name for a tag string, a
function component, or a class instance in warning text.

Application code doesn't usually call into `_warnings` directly beyond
`set_dev_mode`/`is_dev_mode` -- the rest is plumbing used internally by
the component model and flow-control primitives to flag common
reactivity mistakes early.

#### See also

- [`component`][wybthon.component]: raises `warn_destructured_prop` when a
  prop accessor is unwrapped during component setup.
- [`flow`][wybthon.flow]: raises `warn_each_plain_list` when `For` receives
  a static list instead of a signal accessor.
