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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default to the real table. Override to `memory` for a credential-free smoke
# test of the container itself.
ENV PANCHAYAT_BACKEND=dynamodb \
    TIME_SCALE=1

EXPOSE 8080

# Not `python app.py` -- that works, but exec form means signals reach the
# process instead of a shell, so the runtime can actually stop it.
CMD ["python", "app.py"]
