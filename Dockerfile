# Panchayat -- AgentCore Runtime image.
#
# ARM64 IS NOT OPTIONAL. Bedrock AgentCore Runtime runs arm64 only; an amd64
# image builds, pushes, and then fails at deploy with an architecture error
# that does not say "architecture". Build it explicitly:
#
#     docker buildx build --platform linux/arm64 -t panchayat:latest .
#
# The runtime contract this image must satisfy (bedrock_agentcore serves both,
# we only have to not break them):
#     POST /invocations   the entrypoint in app.py
#     GET  /ping          liveness
#     port 8080
#
# 3.12 because numpy>=2.5.3 needs it -- see docs/SETUP.md, that floor is the
# reason a teammate was blocked before writing a line.
#
# Owner: Ali (platform).
FROM --platform=linux/arm64 python:3.12-slim

# Fail fast and log straight through. Without PYTHONUNBUFFERED a crash loop in
# the runtime shows up as empty logs, which is the worst possible way to spend
# an hour on Thursday.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Requirements first, so a code edit does not re-resolve the dependency tree.
# uvicorn and starlette are NOT listed there on purpose: bedrock-agentcore
# declares both (uvicorn>=0.34.2, starlette>=0.46.2) and app.run() imports
# uvicorn lazily, so a missing one would build clean and fail only on the
# first request. Verified against the installed metadata, not assumed.
#
# requirements-prod.txt, NOT requirements.txt. This used to install the `# Dev`
# block too, putting pytest and ruff inside a container that files complaints
# against public bodies -- dead weight at best, and an attack surface on a box
# holding household data at worst.
#
# requirements.txt is untouched: it is one of the three files CLAUDE.md says
# needs all four of us explicitly, and splitting the runtime out additively
# needs none of that. tests/test_requirements.py fails if the shared pins in
# the two files ever disagree, because two dependency files drifting apart is
# a worse problem than the one this solves.
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY . .

# Default to the real table. Override to `memory` for a credential-free smoke
# test of the container itself.
ENV PANCHAYAT_BACKEND=dynamodb \
    TIME_SCALE=1

# Its own ENV on purpose: a `#` comment inside an ENV line-continuation is a
# syntax error, which is how this nearly shipped broken.
#
# BedrockAgentCoreApp.run() picks its own bind address -- 0.0.0.0 only when
# /.dockerenv exists or DOCKER_CONTAINER is set, otherwise 127.0.0.1.
# /.dockerenv is written by the Docker daemon, and nothing promises the
# runtime's container host is Docker. Without this the process starts, logs
# "Uvicorn running on http://127.0.0.1:8080", refuses every request from
# outside the container, and the deploy fails liveness with no application
# error anywhere to read.
ENV DOCKER_CONTAINER=1

EXPOSE 8080

# `opentelemetry-instrument`, not bare python. aws-opentelemetry-distro is
# pinned in requirements.txt and does NOTHING unless the process launches
# through its wrapper -- installed, dormant, and the traces tab empty on
# Thursday with no error to explain it. Exec form so signals reach the
# process instead of a shell, and the runtime can actually stop it.
CMD ["opentelemetry-instrument", "python", "app.py"]
