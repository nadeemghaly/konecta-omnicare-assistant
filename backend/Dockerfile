# Base image ships uv, which installs from the lockfile far faster than pip and
# keeps the image reproducible.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /srv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Dependencies first, in their own layer: application edits then rebuild in
# seconds instead of re-resolving the whole tree.
COPY backend/pyproject.toml backend/uv.lock /srv/
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app /srv/app

# Paths are explicit rather than inferred from the source tree, because the
# container layout differs from the repo layout.
ENV DATA_DIR=/srv/data \
    CHROMA_DIR=/srv/.chroma \
    PATH="/srv/.venv/bin:$PATH"

EXPOSE 8000

# No curl in the slim image, so the healthcheck uses the interpreter that is
# already here. Non-200 raises, which is exactly the failure signal we want.
HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=6 \
    CMD python -c "import urllib.request,sys,json; \
r=urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=4); \
sys.exit(0 if json.load(r)['status']=='healthy' else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
