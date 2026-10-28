from fastapi import HTTPException
from pydantic import BaseModel


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ApiErrorResponse(BaseModel):
    error: ApiErrorDetail
    request_id: str | None = None


def build_error_response(
    code: str,
    message: str,
    field: str | None = None,
    request_id: str | None = None,
) -> ApiErrorResponse:
    return ApiErrorResponse(
        error=ApiErrorDetail(
            code=code,
            message=message,
            field=field,
        ),
        request_id=request_id,
    )


def http_exception(
    status_code: int,
    code: str,
    message: str,
    field: str | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=build_error_response(
            code=code,
            message=message,
            field=field,
        ).model_dump(),
    )
