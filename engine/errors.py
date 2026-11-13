class EngineError(Exception):
    """The input cannot be calculated as given (for example an absent mark under rule `error`)."""


class MethodConfigError(Exception):
    """A method configuration failed validation. The message names the field."""
