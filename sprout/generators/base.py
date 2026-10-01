"""Contract for generation plug-ins."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from PIL import Image

# Params handled by the framework itself, not by a generator's own surface:
# `palette` is resolved by `palettes.resolve_params` and `autotile` is
# injected by the spec loader for `terrain` items. Both are always allowed
# so a spec author never has to special-case them.
FRAMEWORK_PARAMS = frozenset({"palette", "autotile"})


@dataclass
class FrameData:
    id: str
    image: "Image.Image"  # RGBA, frame_px x frame_px
    meta: dict = field(default_factory=dict)


class Generator:
    """Base class. Generators produce deterministic frames given a seed."""

    id = ""

    #: Every ``item.params`` key this generator reads. The spec loader
    #: rejects unknown keys, so a typo in a 300-line mapping fails loudly
    #: instead of silently falling back to a default. ``None`` disables the
    #: check (third-party plug-ins that predate this attribute still work).
    PARAMS: ClassVar[frozenset[str] | None] = None

    def generate(
        self,
        seed: int,
        count: int,
        frame_px: int,
        params: dict,
        base: int = 0,  # global index of the first frame (for position-based variation)
    ) -> list[FrameData]:
        raise NotImplementedError

    @classmethod
    def accepts(cls, params: dict) -> tuple[str, ...]:
        """Unknown keys in ``params`` (empty when the check is disabled)."""
        known = cls.PARAMS
        if known is None:
            return ()
        allowed = known | FRAMEWORK_PARAMS
        return tuple(sorted(k for k in params if k not in allowed))
