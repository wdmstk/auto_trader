"""Pipeline functions for execution reconciliation."""

from __future__ import annotations

from auto_trader.execution.reconciler import ExecutionReconciler


def create_reconciler() -> ExecutionReconciler:
    """Create a default execution reconciler."""
    return ExecutionReconciler()
