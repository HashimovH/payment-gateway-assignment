from pydantic import BaseModel, ConfigDict


class SchemaBase(BaseModel):
    """Shared config for every API schema (request and response bodies)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        from_attributes=True,
    )
