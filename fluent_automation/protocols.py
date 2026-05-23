from typing import Any, Protocol


class MeshingSession(Protocol):
    """このコードで使うMeshing sessionの最小インターフェース。"""

    def watertight(self) -> Any: ...

    def switch_to_solver(self) -> Any: ...

