FROM ghcr.io/astral-sh/uv:python3.13-trixie

WORKDIR /app
ADD pyproject.toml /app
ADD uv.lock /app
RUN CMAKE_ARGS="-DGGML_CUDA=on" uv sync --locked
ADD . /app

# Sync the project into a new environment, asserting the lockfile is up to date
ENV PATH="/app/.venv/bin:$PATH"

RUN python -m uvicorn api:app ${ONSET_PORT:-80}