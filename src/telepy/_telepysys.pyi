# telepysys.pyi

"""
An utility module for telepysys
"""

from types import FrameType

__version__: str

def current_frames() -> dict[int, FrameType]: ...
