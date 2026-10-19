from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator

class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=2000)
    rating: int | None = Field(default=None, ge=1, le=5, strict=True)
    parent_id: int | None = Field(default=None, gt=0)
    anonymous: bool = False
    character: str | None = None

    @model_validator(mode="after")
    def validate_kind(self):
        if self.parent_id is None and (self.rating is None or self.character is not None):
            raise ValueError("La opinión requiere estrellas y no admite personaje.")
        if self.parent_id is not None and self.rating is not None:
            raise ValueError("Las respuestas no llevan estrellas.")
        if self.character and self.anonymous:
            raise ValueError("Una respuesta de personaje no puede ser anónima.")
        return self

class CommentPublic(BaseModel):
    id: int
    parent_id: int | None
    body: str
    rating: int | None
    author_name: str
    character: str | None
    created_at: datetime
