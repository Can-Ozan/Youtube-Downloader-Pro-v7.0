import re
from urllib.parse import urlsplit, urlunsplit


class ValidationError(ValueError):
    """Input cannot safely be used by the application."""


def validate_url(value: str) -> str:
    value = value.strip()
    if len(value) > 8192 or any(ord(c) < 32 or c.isspace() for c in value):
        raise ValidationError("Paste one complete HTTP or HTTPS URL without whitespace.")
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("scheme or host")
        if parsed.username or parsed.password or "\\" in value:
            raise ValueError("credentials or backslash")
        _ = parsed.port
        host = parsed.hostname.encode("idna").decode("ascii")
        if not re.fullmatch(r"[A-Za-z0-9.:[\]-]+", host) or ".." in host:
            raise ValueError("host")
    except (ValueError, UnicodeError) as exc:
        raise ValidationError(
            "Use a valid HTTP or HTTPS URL without embedded credentials."
        ) from exc
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path, parsed.query, ""))


def is_clipboard_media_url(value: str) -> bool:
    try:
        host = urlsplit(validate_url(value)).hostname or ""
    except ValidationError:
        return False
    domains = (
        "youtube.com",
        "youtu.be",
        "vimeo.com",
        "instagram.com",
        "tiktok.com",
        "twitter.com",
        "x.com",
        "facebook.com",
        "soundcloud.com",
    )
    return any(host == domain or host.endswith("." + domain) for domain in domains)


TEMPLATE_FIELDS = {"title", "id", "uploader", "channel", "playlist", "playlist_index", "ext"}
TEMPLATE_TOKEN = re.compile(r"%\((\w+)\)(?:0?[1-6])?[sd]")


def validate_template(value: str) -> str:
    if not value or len(value) > 240 or "\\" in value:
        raise ValidationError("Use a relative filename template of at most 240 characters.")
    parts = value.split("/")
    if any(p in {"", ".", ".."} for p in parts) or len(parts) > 3:
        raise ValidationError("Templates may contain up to two safe subfolders, without '..'.")
    if not value.endswith(".%(ext)s"):
        raise ValidationError("The filename template must end with .%(ext)s.")
    for match in TEMPLATE_TOKEN.finditer(value):
        if match.group(1) not in TEMPLATE_FIELDS:
            raise ValidationError(f"Unsupported template field: {match.group(1)}")
    literal = TEMPLATE_TOKEN.sub("field", value)
    if re.search(r'[%<>:"|?*\x00-\x1f]', literal):
        raise ValidationError("The filename template contains unsafe characters or syntax.")
    return value
