"""AgentCore entrypoint for one simulated institution desk.

Three lines of indirection, for one reason: **the entrypoint must sit at the
root of the package.** Configured as `institutions/a2a_runtime.py`, the
toolkit records the path as it reads it on this machine --
`institutions\\a2a_runtime.py` -- and the runtime, which is Linux, then fails
the endpoint with "The specified entrypoint could not be found or accessed in
your artifact". The runtime itself is created, so the failure looks like a
packaging problem and is a path separator.

`app.py` never hit this because it is already at the root. This is the same
shape for the desks.

Which desk this serves is `PANCHAYAT_DESK`; the behaviour lives in
institutions/a2a_runtime.py.

    agentcore configure -n panchayat_desk_bwssb -e desk_app.py -p A2A
    agentcore launch --agent panchayat_desk_bwssb -env PANCHAYAT_DESK=bwssb ...

Owner: Ali (platform).
"""
from __future__ import annotations

from institutions.a2a_runtime import main

if __name__ == "__main__":
    main()
