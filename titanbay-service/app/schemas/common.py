"""
Common / shared Pydantic schemas used across multiple endpoints.

Defines standardised error response models so that OpenAPI documentation
accurately reflects the error payloads returned by the API.  Without these,
Swagger UI only shows the "happy path" response — API consumers have no
programmatic way to discover the error contract.
"""

from typing import List

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """
    Standard error envelope returned by all non-validation error handlers.

    Every error from the API follows this shape, making it predictable for
    client-side error handling and retry logic.
    """

    error: bool = Field(default=True, description="Always ``true`` for errors")
    message: str = Field(
        ..., description="Human-readable error description", examples=["Fund not found"]
    )


class ValidationErrorDetail(BaseModel):
    """Single field-level validation failure."""

    field: str = Field(
        ...,
        description="Dot-separated path to the invalid field",
        examples=["body -> vintage_year"],
    )
    message: str = Field(
        ...,
        description="Explanation of the validation failure",
        examples=["value is not a valid integer"],
    )


class ValidationErrorResponse(BaseModel):
    """
    Response body for 422 Unprocessable Entity (validation failure).

    Includes a ``details`` array so clients can programmatically map errors
    to individual form fields in the UI.
    """

    error: bool = Field(default=True, description="Always ``true`` for errors")
    message: str = Field(
        default="Validation failed",
        description="Summary message",
    )
    details: List[ValidationErrorDetail] = Field(..., description="Per-field validation failures")
