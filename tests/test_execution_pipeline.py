"""Unit tests for execution pipeline."""

from __future__ import annotations

from auto_trader.execution.pipeline import create_reconciler
from auto_trader.execution.reconciler import ExecutionReconciler


class TestPipeline:
    """Test execution pipeline functions."""

    def test_create_reconciler(self) -> None:
        """Test default reconciler creation."""
        reconciler = create_reconciler()
        assert isinstance(reconciler, ExecutionReconciler)
        assert reconciler is not None
