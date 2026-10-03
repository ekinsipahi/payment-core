class CardBlocked(ValueError):
    """A card attempt was refused by the guard (disposable email, cooldown, or
    velocity). Subclasses ValueError so existing views that map ValueError -> HTTP
    400 keep working unchanged; the message is customer-safe (never leaks which
    signal tripped). ``retry_after`` is the suggested wait in seconds, or None."""

    def __init__(self, message, *, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after
