from enum import Enum


class State(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
