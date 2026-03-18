"""LangExtract few-shot examples placeholder (Phase 2).

In Phase 2, this module should provide `lx.data.ExampleData` instances
illustrating what credit-relevant signals look like for SIS extraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import langextract as lx


def get_sis_example_data() -> list["lx.data.ExampleData"]:
    """Return SIS few-shot `ExampleData` for LangExtract.

    Returns:
        A list of LangExtract ExampleData objects.
    """

    raise NotImplementedError("Phase 2/3/4")

