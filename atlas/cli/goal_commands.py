"""
Atlas CLI — Goal Execution Management (Phase 15.4).

CLI is presentation only.
Delegates all business logic to GoalExecutionEngine.
Never calls GoalRepository, ExecutionGateway, or ToolEngine directly.

Follows the same pattern as ``evolution_commands.py``.
"""

from datetime import datetime
from typing import Any

from atlas.goals.models import GoalStatus


def _format_goal(goal: Any) -> str:
    """Format a single improvement goal for display."""
    return (
        f"  [{goal.goal_id}] {goal.title}\n"
        f"       Status: {goal.status.name}\n"
        f"       Category: {goal.category.name}\n"
        f"       Priority: {goal.priority.name}\n"
        f"       Created: {goal.proposed_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"       Description: {goal.description[:120]}"
    )


def cmd_goals_list(engine: Any, args: Any) -> str:
    """
    List all improvement goals.

    CLI: atlas goals list
         atlas goals list --status approved

    Delegates to: GoalExecutionEngine.repository.get_all_goals()
    """
    status_filter = getattr(args, "status", "")

    repo = engine.repository
    if status_filter:
        try:
            status_enum = GoalStatus[status_filter.upper()]
            goals = repo.get_goals_by_status(status_enum)
        except KeyError:
            return f"Error: Unknown status '{status_filter}'. "
            f"Valid: {', '.join(s.name for s in GoalStatus)}"
    else:
        goals = repo.get_all_goals()

    if not goals:
        if status_filter:
            return f"No goals found with status '{status_filter}'."
        return "No goals found."

    lines = [f"Found {len(goals)} goal(s):\n"]
    for g in goals:
        lines.append(_format_goal(g))
        lines.append("")

    return "\n".join(lines).strip()


def cmd_goals_show(engine: Any, args: Any) -> str:
    """
    Show full details of a single improvement goal.

    CLI: atlas goals show <goal_id>

    Delegates to: GoalExecutionEngine.repository.get_goal()
    """
    goal_id = getattr(args, "goal_id", "")
    if not goal_id:
        return "Error: goal_id is required."

    repo = engine.repository
    goal = repo.get_goal(goal_id)
    if goal is None:
        return f"Goal '{goal_id}' not found."

    lines = [
        f"Goal: {goal.goal_id}",
        f"Title: {goal.title}",
        f"Description: {goal.description}",
        f"Status: {goal.status.name}",
        f"Category: {goal.category.name}",
        f"Priority: {goal.priority.name}",
        f"Confidence: {goal.confidence:.2f}",
        f"Evidence Count: {goal.evidence_count}",
        f"Proposed: {goal.proposed_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Updated: {goal.updated_at.strftime('%Y-%m-%d %H:%M:%S')}",
    ]

    # Show authorization if present
    auth = repo.get_authorization(goal_id)
    if auth is not None:
        lines.append("")
        lines.append("Authorization:")
        lines.append(f"  Authorized by: {auth.authorized_by}")
        lines.append(f"  Authorized at: {auth.authorized_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if auth.comment:
            lines.append(f"  Comment: {auth.comment}")
        if auth.strategy_key:
            lines.append(f"  Strategy: {auth.strategy_name} ({auth.strategy_key})")
        if auth.planning_context_version:
            lines.append(f"  Planning Context: {auth.planning_context_version}")

    return "\n".join(lines)


def cmd_goals_activate(engine: Any, args: Any) -> str:
    """
    Authorize a goal for execution.

    CLI: atlas goals activate <goal_id> --comment "optional..."

    Delegates to: GoalExecutionEngine.activate()
    """
    goal_id = getattr(args, "goal_id", "")
    if not goal_id:
        return "Error: goal_id is required."

    comment = getattr(args, "comment", "")

    result = engine.activate(goal_id=goal_id, comment=comment)

    if result.success:
        output = f"Goal '{goal_id}' activated (status: {result.status})."
        summary = result.execution_summary
        strategy = summary.get("strategy_key", "")
        if strategy:
            output += f"\n  Strategy: {strategy}"
        return output

    return f"Failed to activate goal '{goal_id}': {result.error}"


def cmd_goals_history(engine: Any, args: Any) -> str:
    """
    Show execution history for goals.

    CLI: atlas goals history
         atlas goals history <goal_id>

    Delegates to: GoalExecutionEngine.repository.get_execution_records()
    """
    goal_id = getattr(args, "goal_id", "")

    repo = engine.repository
    records = repo.get_execution_records(goal_id=goal_id, n=50)

    if not records:
        if goal_id:
            return f"No execution records found for goal '{goal_id}'."
        return "No execution records found."

    title = (
        f"Execution history for goal '{goal_id}'"
        if goal_id
        else "Recent execution records"
    )
    lines = [f"{title} ({len(records)} record(s)):\n"]

    for r in records:
        status_icon = "OK" if r.outcome.name == "COMPLETED" else "FAIL"
        lines.append(
            f"  [{r.record_id}] {status_icon} "
            f"Goal: {r.goal_id} "
            f"Outcome: {r.outcome.name} "
            f"Tool: {r.action_tool or 'none'} "
            f"Time: {r.started_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if r.error:
            lines.append(f"       Error: {r.error[:120]}")
        if r.strategy_key:
            lines.append(f"       Strategy: {r.strategy_name} ({r.strategy_key})")

    return "\n".join(lines).strip()