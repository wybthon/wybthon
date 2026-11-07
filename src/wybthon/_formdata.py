"""`FormData`: a submitted form's fields, the argument a form action receives.

The same class arrives on both sides: in the browser it's built from the
submitted `<form>`, and on the server from the request body of a
JavaScript-free post (URL-encoded or multipart).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, overload
from urllib.parse import parse_qsl, urlencode

__all__ = ["FormData", "UploadedFile"]


@dataclass(frozen=True, slots=True)
class UploadedFile:
    """A file submitted with a form.

    Attributes:
        filename: The name the browser sent.
        content_type: The file's media type.
        data: The file's bytes.
    """

    filename: str
    content_type: str
    data: bytes

    @property
    def size(self) -> int:
        """The file's size in bytes."""
        return len(self.data)


class FormData:
    """A form's fields in submission order; a name may appear more than once.

    Read it like a mapping (`form["title"]`, `form.get("title")`,
    `"done" in form`) for the last value of a field, and with
    [`get_all`][wybthon.FormData.get_all] for every value. A text field's
    value is a `str`, a file input's an [`UploadedFile`][wybthon.UploadedFile].

    ```python
    @form_action
    @server_function
    async def add_todo(form: FormData) -> None:
        await db.todos.add(title=form["title"], done="done" in form)
    ```
    """

    __slots__ = ("_items",)

    def __init__(self, items: Any = None) -> None:
        if items is None:
            self._items: list[tuple[str, str | UploadedFile]] = []
        elif isinstance(items, FormData):
            self._items = list(items._items)
        elif isinstance(items, dict):
            self._items = [(str(key), value) for key, value in items.items()]
        else:
            self._items = [(str(key), value) for key, value in items]

    @overload
    def get(self, name: str) -> str | UploadedFile | None: ...

    @overload
    def get[D](self, name: str, default: D) -> str | UploadedFile | D: ...

    def get(self, name: str, default: Any = None) -> Any:
        """The last value of field `name`, or `default`."""
        for key, value in reversed(self._items):
            if key == name:
                return value
        return default

    def get_all(self, name: str) -> list[str | UploadedFile]:
        """Every value of field `name`, in submission order."""
        return [value for key, value in self._items if key == name]

    def __getitem__(self, name: str) -> str | UploadedFile:
        for key, value in reversed(self._items):
            if key == name:
                return value
        raise KeyError(name)

    def __contains__(self, name: object) -> bool:
        return any(key == name for key, _ in self._items)

    def __iter__(self) -> Iterator[str]:
        return iter(dict.fromkeys(key for key, _ in self._items))

    def __len__(self) -> int:
        return len(dict.fromkeys(key for key, _ in self._items))

    def keys(self) -> list[str]:
        """The field names, each once, in submission order."""
        return list(self)

    def items(self) -> list[tuple[str, str | UploadedFile]]:
        """Every `(name, value)` pair, in submission order."""
        return list(self._items)

    def append(self, name: str, value: str | UploadedFile) -> None:
        """Add a value for `name`."""
        self._items.append((name, value))

    def to_dict(self) -> dict[str, str | UploadedFile]:
        """Each field's last value."""
        return dict(self._items)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FormData) and other._items == self._items

    def __repr__(self) -> str:
        return f"FormData({self._items!r})"

    # -- encoding ---------------------------------------------------------

    def encode(self) -> tuple[str, bytes]:
        """`(content type, body)` for sending these fields in a request."""
        if not any(isinstance(value, UploadedFile) for _, value in self._items):
            body = urlencode([(key, value) for key, value in self._items]).encode()
            return "application/x-www-form-urlencoded", body
        boundary = "wyb" + __import__("secrets").token_hex(12)
        parts: list[bytes] = []
        for key, value in self._items:
            name = key.replace('"', "%22")
            if isinstance(value, UploadedFile):
                filename = value.filename.replace('"', "%22")
                head = (
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                    f"Content-Type: {value.content_type or 'application/octet-stream'}\r\n\r\n"
                )
                parts.append(f"--{boundary}\r\n".encode() + head.encode() + value.data + b"\r\n")
            else:
                head = f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                parts.append(f"--{boundary}\r\n".encode() + head.encode() + str(value).encode() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        return f"multipart/form-data; boundary={boundary}", b"".join(parts)

    @classmethod
    def parse(cls, content_type: str, body: bytes) -> FormData:
        """Parse a URL-encoded or multipart request body."""
        kind = content_type.split(";", 1)[0].strip().lower()
        if kind == "application/x-www-form-urlencoded":
            return cls(parse_qsl(body.decode("utf-8", "replace"), keep_blank_values=True))
        if kind == "multipart/form-data":
            import email.parser
            import email.policy

            message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
                b"Content-Type: " + content_type.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
            )
            form = cls()
            if not message.is_multipart():
                return form
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if name is None:
                    continue
                filename = part.get_filename()
                raw = part.get_payload(decode=True)
                payload = raw if isinstance(raw, bytes) else b""
                if filename is not None:
                    form.append(str(name), UploadedFile(filename, part.get_content_type(), payload))
                else:
                    charset = part.get_content_charset() or "utf-8"
                    form.append(str(name), payload.decode(charset, "replace"))
            return form
        raise ValueError(f"Unsupported form encoding: {content_type or 'none'}")
