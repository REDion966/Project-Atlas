"""
Atlas Built-in Tools

Default tools registered during Atlas startup.
These provide basic tool intelligence capabilities.

Phase 6.9 — Tool Intelligence Foundation.
"""

from atlas.tools.models import Tool, ToolParameter, ToolResult


def _echo_handler(params: dict) -> ToolResult:
    """
    Echo handler — returns the input parameters as output.

    This is a demonstration tool that validates the tool execution
    pipeline without performing any real system operations.

    Args:
        params: The parameters to echo back.

    Returns:
        A ToolResult containing the input parameters in the output.
    """
    return ToolResult(
        tool_name="echo",
        success=True,
        output={"echoed": dict(params)},
        metadata={"handler": "echo"},
    )


def _list_tools_handler(params: dict) -> ToolResult:
    """
    List tools handler — returns information about registered tools.

    This handler is designed to be called through ToolEngine, which
    provides access to the registry. When called directly, it returns
    a placeholder result.

    Args:
        params: May contain a "tools" key with a list of Tool
            instances to describe.

    Returns:
        A ToolResult containing tool descriptions.
    """
    tools_data = params.get("tools", [])
    if tools_data:
        tool_list = [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "tags": list(t.tags),
            }
            for t in tools_data
        ]
    else:
        tool_list = []

    return ToolResult(
        tool_name="list_tools",
        success=True,
        output={"tools": tool_list},
        metadata={"handler": "list_tools"},
    )


ECHO_TOOL = Tool(
    name="echo",
    description="Returns the input parameters as output. Useful for testing and debugging the tool execution pipeline.",
    parameters=[
        ToolParameter(
            name="message",
            description="The message to echo back.",
            type_hint="string",
            required=False,
        ),
    ],
    category="utility",
    handler=_echo_handler,
    tags=["debug", "test", "utility"],
    metadata={"builtin": True, "version": "1.0.0"},
)

LIST_TOOLS_TOOL = Tool(
    name="list_tools",
    description="Returns a list of all registered tools with their names, descriptions, categories, and tags.",
    parameters=[
        ToolParameter(
            name="tools",
            description="List of Tool instances to describe (injected by ToolEngine).",
            type_hint="list",
            required=False,
        ),
    ],
    category="utility",
    handler=_list_tools_handler,
    tags=["discovery", "utility", "help"],
    metadata={"builtin": True, "version": "1.0.0"},
)

BUILTIN_TOOLS: list[Tool] = [
    ECHO_TOOL,
    LIST_TOOLS_TOOL,
]
"""
List of built-in tools registered during Atlas startup.
"""