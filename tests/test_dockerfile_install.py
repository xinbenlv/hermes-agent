from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"


def test_dockerfile_uses_uv_venv_for_all_extras_install():
    content = DOCKERFILE.read_text(encoding="utf-8")

    assert 'ENV VIRTUAL_ENV=/opt/hermes/.venv' in content
    assert 'ENV PATH="$VIRTUAL_ENV/bin:$PATH"' in content
    assert 'pip install --no-cache-dir uv --break-system-packages' in content
    assert 'uv venv "$VIRTUAL_ENV"' in content
    assert 'uv pip install --python "$VIRTUAL_ENV/bin/python" -e ".[all]"' in content
    assert 'pip install --no-cache-dir -e ".[all]" --break-system-packages' not in content
