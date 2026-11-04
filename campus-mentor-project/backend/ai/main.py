"""추출 API는 app.main 한곳으로 모았다. `uvicorn app.main:app` 으로 실행한다."""

from app.main import app

__all__ = ["app"]
