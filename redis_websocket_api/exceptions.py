class APIError(Exception):
    """Base exception for errors raised by high-level websocket API."""


class MessageHandlerError(APIError):
    """Decoding or parsing a message failed."""


class RemoteMessageHandlerError(MessageHandlerError):
    """Raised for errors directly caused by messages from the client."""


class InternalMessageHandlerError(MessageHandlerError):
    """Raised for errors directly caused by messages from internal sources."""
