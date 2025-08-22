FROM nvidia/cuda:12.9.1-cudnn-devel-ubuntu24.04 AS build-stage

RUN apt-get update && apt-get install -y  --no-install-recommends cmake build-essential curl ca-certificates

# Download the latest installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh

# Run the installer then remove it
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin/:$PATH"

WORKDIR /app
ADD pyproject.toml /app
ADD uv.lock /app
RUN CMAKE_ARGS="-DGGML_CUDA=on" uv sync --locked


FROM ghcr.io/astral-sh/uv:python3.13-trixie AS production-stage




WORKDIR /app
COPY --from=build-stage /app/.venv  /app/.venv

ADD . /app

# Sync the project into a new environment, asserting the lockfile is up to date
ENV PATH="/app/.venv/bin:$PATH"

RUN python -m uvicorn api:app ${ONSET_PORT:-80}