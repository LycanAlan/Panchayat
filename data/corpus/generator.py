"""Synthetic claim corpus. MUST be blind to core.scoring -- do not import it.

Owner: Kartik
Lane: data + mesh
"""

"""Failure model first, claims second.

Pick a feeder, decide it fails, decide which households notice and which of
those bother to report. Then emit claims. If this file imports core.scoring the
density curve becomes circular and the result is worthless.
"""


def generate(n_households: int, days: int, seed: int = 0) -> list:
    raise NotImplementedError
