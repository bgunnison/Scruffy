from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


PrimitiveType = Literal["cube", "sphere", "cylinder", "cone", "plane", "torus"]


class Color(BaseModel):
    r: float = Field(0.8)
    g: float = Field(0.8)
    b: float = Field(0.8)

    @field_validator("r", "g", "b")
    @classmethod
    def clamp_unit(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class Transform(BaseModel):
    location: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation_degrees: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])


class Keyframe(BaseModel):
    time: float
    location: Optional[List[float]] = None
    rotation_degrees: Optional[List[float]] = None
    scale: Optional[List[float]] = None


class Animation(BaseModel):
    location_keys: List[Keyframe] = Field(default_factory=list)
    rotation_keys: List[Keyframe] = Field(default_factory=list)
    scale_keys: List[Keyframe] = Field(default_factory=list)


class ObjectSpec(BaseModel):
    name: str
    type: PrimitiveType
    color: Color = Field(default_factory=Color)
    dimensions: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    transform: Transform = Field(default_factory=Transform)
    animation: Optional[Animation] = None


class CameraSpec(BaseModel):
    name: str = "Camera"
    transform: Transform = Field(default_factory=Transform)
    look_at: Optional[List[float]] = None
    animation: Optional[Animation] = None
    focal_length_mm: float = 35.0


class RenderSettings(BaseModel):
    duration_seconds: float = 5.0
    fps: int = 24
    resolution_x: int = 1280
    resolution_y: int = 720
    background_color: Color = Field(default_factory=lambda: Color(r=0.05, g=0.08, b=0.12))


class ScenePlan(BaseModel):
    version: str = "1.0"
    description: Optional[str] = None
    render: RenderSettings = Field(default_factory=RenderSettings)
    camera: CameraSpec = Field(default_factory=CameraSpec)
    objects: List[ObjectSpec] = Field(default_factory=list)

    def json_schema(self) -> dict:
        return self.model_json_schema()
