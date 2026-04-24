"""
Narration Audio Repository
Stores slide-level TTS audio cache entries.
MongoDB-backed implementation.
"""

import time
from typing import Optional, List

from ..database.repositories import NarrationAudioRepository
from ..database.models import NarrationAudio


__all__ = ["NarrationAudioRepository", "NarrationAudio"]
