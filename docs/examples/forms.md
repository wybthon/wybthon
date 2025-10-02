### Forms

Bindings and validation.

```python
from wybthon.forms import form_state, bind_text, required
from wybthon import h

fields = form_state({"email": ""})

def View(props):
    email = fields["email"]
    return h("form", {"on_submit": lambda e: print("submit")},
             h("input", {**bind_text(email, validators=[required()])}),
             h("div", {}, email.error.get() or ""))
```

> TODO: Add checkbox/select and a full submit handler.
