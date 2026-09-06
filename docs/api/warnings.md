### wybthon._warnings

::: wybthon._warnings

#### What's in this module

`_warnings` is Wybthon's lightweight development-mode diagnostics
layer. It gives the framework a single place to surface actionable
warnings and error tracebacks while developing. Warning output and
exception tracebacks can be disabled for production; error messages
still go to `stderr`.

Three things live here:

- **Dev-mode toggling**: [`DEV_MODE`][wybthon._warnings.DEV_MODE]
  defaults to `True`. Call
  [`set_dev_mode(False)`][wybthon._warnings.set_dev_mode] at startup
  to silence warnings and traceback printing for production builds.
  This also disables [`WriteInScopeError`][wybthon.WriteInScopeError]
  for signal and store writes inside tracking scopes.
  [`is_dev_mode()`][wybthon._warnings.is_dev_mode] reports the current
  state. Both are re-exported from the top-level `wybthon` package.
- **Warnings**: [`warn`][wybthon._warnings.warn] prints a
  message to `stderr` every time it's called (a no-op when dev mode is
  off), while [`warn_once`][wybthon._warnings.warn_once] deduplicates
  by a `(category, key)` pair so repeated calls with the same pair
  only log once per process. The reactive system uses this path for
  untracked reads of signals, memos, and props at the top level of a
  component body. [`warn_each_plain_list`][wybthon._warnings.warn_each_plain_list]
  also uses it when `For` receives a static list or tuple.
- **Error logging**: [`log_error`][wybthon._warnings.log_error] always
  prints, regardless of `DEV_MODE`; in dev mode it also prints the full
  traceback of an attached exception.

`component_name` is a small formatting helper shared by the warning
functions above to produce a readable name for a tag string, a
function component, or a class instance in warning text.

Application code doesn't usually call into `_warnings` directly beyond
`set_dev_mode`/`is_dev_mode`. The other helpers are used internally by
the reactive system and flow-control primitives to flag common
reactivity mistakes early.

#### See also

- [Reactivity](../concepts/reactivity.md): explains tracked reads and
  the `WriteInScopeError` diagnostic.
- [`flow`][wybthon.flow]: calls `warn_each_plain_list` when `For` receives
  a static list or tuple instead of an accessor.
