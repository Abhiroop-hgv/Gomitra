"""Request bodies of the HTTP API (validated by Pydantic). Responses are plain JSON built by the services."""
from pydantic import BaseModel


class Register(BaseModel):
    name: str = ""
    tag: str
    breed: str = ""
    age: str = ""
    photos: dict[str, str]          # front / left / right / back as data URLs


class Analyze(BaseModel):
    image: str
    mode: str = "photo"             # "photo" = farmer upload (whole image), "cctv" = camera frame (find cows first)
    camera: str = "Camera 1"
    cow_id: str | None = None       # when the farmer already knows which cow it is
    read_tags: bool = False


class AudioIn(BaseModel):
    audio: str
    camera: str = "Camera 1"
    immediate: bool = False         # demo clips: alert from one clip instead of waiting for agreement


class Credentials(BaseModel):
    username: str
    password: str


class NewUser(BaseModel):
    username: str
    password: str
    name: str = ""
    phone: str = ""


class NotifySettings(BaseModel):
    phone: str                      # international form, +919876543210
    lang: str = "en"                # language of the SMS: en / hi / te
    enabled: bool = True
    min_severity: str = "medium"    # "high" = only urgent alerts


class Posture(BaseModel):
    images: list[str]               # 1 to 5 pictures of the same cow (frames of a short walking clip, or a photo)
    cow_id: str | None = None
    camera: str = "Camera 1"


class Ingest(BaseModel):
    file: str                       # base64 of one photo, one sound clip or one short video
    camera: str = "Camera 1"


class Ask(BaseModel):
    question: str
    lang: str = "en"
    cow_id: str | None = None


class KbDoc(BaseModel):
    source: str
    text: str | None = None
    pdf: str | None = None          # base64 of a PDF
