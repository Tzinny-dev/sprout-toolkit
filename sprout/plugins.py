"""Third-party generator discovery via Python entry points.

A distribution extends the toolkit by advertising its generators under the
``sprout.generators`` entry-point group::

    [project.entry-points."sprout.generators"]
    vehicle = "sprout_vehicles:Vehicle"

The loaded object must be a ``Generator`` subclass (or the class itself).
Discovery is deliberately forgiving: a distribution that raises on import,
points at a missing attribute, or exposes a non-``Generator`` object is
skipped instead of breaking every spec of the user who merely has it
installed. Built-in generators always win an id collision, so installing a
plug-in can never change the output of an existing spec.

The toolkit never needs to know what a plug-in draws — a plug-in is
responsible for its own vocabulary, and its ``PARAMS`` surface (when
declared) is validated exactly like a built-in's.
"""
from __future__ import annotations

from importlib.metadata import entry_points

ENTRY_POINT_GROUP = "sprout.generators"


def discover(group: str = ENTRY_POINT_GROUP) -> dict[str, type]:
    """Load third-party generators as ``{id: class}``.

    Duplicate ids across distributions resolve to the first one found, in
    the order ``importlib.metadata`` reports. A plug-in that fails to load
    is dropped silently: a broken optional dependency must not make the
    built-in generators unusable.
    """
    from .generators.base import Generator  # local: avoids an import cycle

    found: dict[str, type] = {}
    for ep in entry_points(group=group):
        try:
            obj = ep.load()
        except Exception:  # noqa: BLE001 - any failure means "skip it"
            continue
        cls = obj if isinstance(obj, type) else type(obj)
        if not issubclass(cls, Generator):
            continue
        gen_id = getattr(cls, "id", "")
        if not isinstance(gen_id, str) or not gen_id:
            continue
        found.setdefault(gen_id, cls)
    return found


def load_into(registry: dict[str, type], group: str = ENTRY_POINT_GROUP) -> list[str]:
    """Merge discovered generators into ``registry``; returns the ids added.

    Ids already present are kept as-is — a plug-in must not be able to
    shadow a built-in generator.
    """
    added = []
    for gen_id, cls in discover(group).items():
        if gen_id in registry:
            continue
        registry[gen_id] = cls
        added.append(gen_id)
    return sorted(added)