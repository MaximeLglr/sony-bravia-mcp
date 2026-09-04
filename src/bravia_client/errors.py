from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorPayload(BaseModel):
    error: str
    message: str
    hint: str
    model_config = {"extra": "allow"}


class BraviaError(Exception):
    code = "UNKNOWN"
    default_message = "An unexpected error occurred."
    hint = "An unexpected error occurred."

    def __init__(self, message: str | None = None, **extra: Any):
        self.message = message or self.default_message
        self.extra = extra
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return ErrorPayload(
            error=self.code, message=self.message, hint=self.hint, **self.extra
        ).model_dump()


class TVUnreachable(BraviaError):
    code = "TV_UNREACHABLE"
    default_message = "The TV is not responding."
    hint = (
        "The TV is unreachable. It may be unplugged, in deep standby, or off the "
        "network. Try set_power(on=true)."
    )


class TVStandby(BraviaError):
    code = "TV_STANDBY"
    default_message = "The TV responded but is powered off."
    hint = "The TV is in standby. Call set_power(on=true) before acting."


class WebApiUnavailable(BraviaError):
    code = "WEBAPI_UNAVAILABLE"
    default_message = "The WebApiCore service stopped responding after several attempts."
    hint = (
        "The internal TV service hosting the API is frozen. A full TV restart is "
        "needed: hold the power button on the remote, then choose Restart."
    )


class AuthFailed(BraviaError):
    code = "AUTH_FAILED"
    default_message = "The pre-shared key was rejected."
    hint = (
        "The pre-shared key was rejected. Check BRAVIA_PSK and the TV's "
        "Authentication setting (Normal and Pre-Shared Key)."
    )


class InputNotFound(BraviaError):
    code = "INPUT_NOT_FOUND"
    default_message = "No input matches the requested name."
    hint = "No input matches. Call list_inputs for the valid names."


class AppNotFound(BraviaError):
    code = "APP_NOT_FOUND"
    default_message = "No application matches the requested name."
    hint = "No application matches. Call list_apps for the valid names."


class UnsupportedMethod(BraviaError):
    code = "UNSUPPORTED_METHOD"
    default_message = "The method does not exist on this firmware."
    hint = "This function is unavailable on this model or firmware. Do not retry."


class BadRequest(BraviaError):
    code = "BAD_REQUEST"
    default_message = "Invalid parameters."
    hint = "The provided parameters are invalid. Check the call."


SONY_ERROR_MAP: dict[int, type[BraviaError]] = {
    403: AuthFailed,
    404: UnsupportedMethod,
    12: UnsupportedMethod,
    501: UnsupportedMethod,
    7: TVStandby,
    3: BadRequest,
    5: BadRequest,
    40005: TVStandby,
}
