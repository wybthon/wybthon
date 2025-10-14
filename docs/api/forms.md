### wybthon.forms

::: wybthon.forms

Additional helpers introduced:

- validate_field
- validate_form
- on_submit_validated
- rules_from_schema
- a11y_control_attrs
- error_message_attrs

#### Schema-based rules

`rules_from_schema(schema: Dict[str, Dict[str, Any]]) -> Dict[str, List[Validator]]`

Build a validators map from a lightweight schema. Supported per-field keys:

- `required`: bool or str (custom message)
- `min_length`: int (optional `min_length_message`)
- `max_length`: int (optional `max_length_message`)
- `email`: bool or str (custom message)

Example:

```python
schema = {
    "name": {"required": True, "min_length": 2},
    "email": {"email": True},
}
rules = rules_from_schema(schema)
```
