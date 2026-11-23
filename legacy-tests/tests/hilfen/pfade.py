from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "spec"
OPENAPI = SPEC / "api" / "openapi.yaml"
FIXTURES = REPO / "fixtures"
KMY = FIXTURES / "kmy"
MOCK = FIXTURES / "mock"
