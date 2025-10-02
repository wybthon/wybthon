### Forms

Form state helpers and validators.

```python
from wybthon.forms import form_state, bind_text, required, min_length
from wybthon import h

fields = form_state({"email": "", "agree": False})

def View(props):
    email = fields["email"]
    return h("form", {"on_submit": lambda e: print("submit")},
             h("input", {**bind_text(email, validators=[required(), min_length(3)])}),
             h("div", {}, email.error.get() or ""))
```

> TODO: Add checkbox/select bindings and `on_submit` example with validation.
