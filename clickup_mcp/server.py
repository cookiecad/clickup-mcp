from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Mapping, Optional

from fastmcp import FastMCP

from .clickup_api import ClickUpAPIError, ClickUpClient, ClickUpV3Client
from .config import Settings


settings = Settings()
settings.validate()

client = ClickUpClient(api_token=settings.api_token, base_url=settings.api_base_url, debug_http=settings.debug_http)
client_v3 = ClickUpV3Client(api_token=settings.api_token, base_url=settings.api_v3_base_url, debug_http=settings.debug_http)

mcp = FastMCP("clickup")


def _ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _now_ms() -> int:
    return _ms(datetime.now(timezone.utc))


async def _get_default_team_id() -> str:
    if settings.team_id:
        return settings.team_id
    teams = await client.request("GET", "/team")
    # Typical: {"teams":[{"id":"...","name":"..."}]}
    team_list = teams.get("teams") if isinstance(teams, dict) else None
    if not team_list:
        raise RuntimeError("No teams returned by ClickUp; set CLICKUP_TEAM_ID")
    team_id = str(team_list[0].get("id"))
    settings.team_id = team_id
    settings.workspace_id = team_id
    return team_id


async def _get_default_workspace_id() -> str:
    """Get workspace_id for v3 API (same as team_id)."""
    return await _get_default_team_id()


def _clean_params(params: Mapping[str, Any] | None) -> Dict[str, Any] | None:
    if not params:
        return None
    out: Dict[str, Any] = {}
    for k, v in params.items():
        if v is None:
            continue
        out[k] = v
    return out


async def _api_get_task(task_id: str, *, include_subtasks: bool = False) -> dict:
    params = {"include_subtasks": str(include_subtasks).lower()}
    res = await client.request("GET", f"/task/{task_id}", params=params)
    return res if isinstance(res, dict) else {"data": res}


async def _api_create_task(list_id: str, body: Dict[str, Any]) -> dict:
    res = await client.request("POST", f"/list/{list_id}/task", json_body=body)
    return res if isinstance(res, dict) else {"data": res}


async def _api_search_tasks(team_id: str, params: Dict[str, Any]) -> dict:
    res = await client.request("GET", f"/team/{team_id}/task", params=_clean_params(params) or {})
    return res if isinstance(res, dict) else {"data": res}


@mcp.tool
async def clickup_context() -> dict:
    """
    Return resolved ClickUp context (team/workspace id and current user).
    """
    team_id = await _get_default_team_id()
    user = await client.request("GET", "/user")
    return {
        "api_base_url": settings.api_base_url,
        "team_id": team_id,
        "user": user,
    }


# -------- Browsing --------

@mcp.tool
async def list_teams() -> dict:
    """List ClickUp teams (workspaces)."""
    return await client.request("GET", "/team")


@mcp.tool
async def get_team(team_id: str) -> dict:
    """Get a team (workspace) by id."""
    return await client.request("GET", f"/team/{team_id}")


@mcp.tool
async def list_spaces(team_id: Optional[str] = None, archived: bool = False) -> dict:
    """List spaces for a team (workspace)."""
    team_id = team_id or await _get_default_team_id()
    return await client.request("GET", f"/team/{team_id}/space", params={"archived": str(archived).lower()})


@mcp.tool
async def list_folders(space_id: str, archived: bool = False) -> dict:
    """List folders within a space."""
    return await client.request("GET", f"/space/{space_id}/folder", params={"archived": str(archived).lower()})


@mcp.tool
async def list_lists_in_space(space_id: str, archived: bool = False) -> dict:
    """List lists within a space (folderless lists)."""
    return await client.request("GET", f"/space/{space_id}/list", params={"archived": str(archived).lower()})


@mcp.tool
async def list_lists_in_folder(folder_id: str, archived: bool = False) -> dict:
    """List lists within a folder."""
    return await client.request("GET", f"/folder/{folder_id}/list", params={"archived": str(archived).lower()})


@mcp.tool
async def list_tasks_in_list(
    list_id: str,
    include_subtasks: bool = False,
    include_closed: Optional[bool] = None,
    order_by: Optional[str] = "updated",
    reverse: Optional[bool] = True,
    page: int = 0,
) -> dict:
    """List tasks in a specific list."""
    params = _clean_params(
        {
            "include_subtasks": str(bool(include_subtasks)).lower(),
            "include_closed": str(bool(include_closed)).lower() if include_closed is not None else None,
            "order_by": order_by,
            "reverse": str(bool(reverse)).lower() if reverse is not None else None,
            "page": page,
        }
    ) or {}
    return await client.request("GET", f"/list/{list_id}/task", params=params)


# -------- Tasks CRUD --------

@mcp.tool
async def get_task(task_id: str, include_subtasks: bool = False) -> dict:
    """Get a task by id."""
    return await _api_get_task(task_id, include_subtasks=include_subtasks)


@mcp.tool
async def create_task(
    list_id: str,
    name: str,
    description: Optional[str] = None,
    markdown_description: bool = True,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assignees: Optional[List[int]] = None,
    tags: Optional[List[str]] = None,
    due_date_ms: Optional[int] = None,
    start_date_ms: Optional[int] = None,
    parent_task_id: Optional[str] = None,
    custom_fields: Optional[List[dict]] = None,
) -> dict:
    """
    Create a task in a list.

    Notes:
    - ClickUp uses epoch milliseconds for dates (`*_ms`).
    - Create a subtask by setting `parent_task_id`.
    """
    body: Dict[str, Any] = {"name": name}
    if description is not None:
        body["description"] = description
        body["markdown_description"] = bool(markdown_description)
    if status is not None:
        body["status"] = status
    if priority is not None:
        body["priority"] = priority
    if assignees is not None:
        body["assignees"] = assignees
    if tags is not None:
        body["tags"] = tags
    if due_date_ms is not None:
        body["due_date"] = due_date_ms
    if start_date_ms is not None:
        body["start_date"] = start_date_ms
    if parent_task_id is not None:
        body["parent"] = parent_task_id
    if custom_fields is not None:
        body["custom_fields"] = custom_fields

    return await _api_create_task(list_id, body)


@mcp.tool
async def create_subtask(
    parent_task_id: str,
    name: str,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assignees: Optional[List[int]] = None,
    tags: Optional[List[str]] = None,
    due_date_ms: Optional[int] = None,
    start_date_ms: Optional[int] = None,
    custom_fields: Optional[List[dict]] = None,
) -> dict:
    """
    Convenience: create a subtask under an existing task (auto-detects list_id).
    """
    # IMPORTANT: don't call @mcp.tool functions from other tools; FastMCP wraps them.
    parent = await _api_get_task(parent_task_id)
    list_id = str(((parent.get("list") or {}).get("id")) or "")
    if not list_id:
        raise RuntimeError("Could not determine list_id from parent task")
    body: Dict[str, Any] = {"name": name, "parent": parent_task_id}
    if description is not None:
        body["description"] = description
        body["markdown_description"] = True
    if status is not None:
        body["status"] = status
    if priority is not None:
        body["priority"] = priority
    if assignees is not None:
        body["assignees"] = assignees
    if tags is not None:
        body["tags"] = tags
    if due_date_ms is not None:
        body["due_date"] = due_date_ms
    if start_date_ms is not None:
        body["start_date"] = start_date_ms
    if custom_fields is not None:
        body["custom_fields"] = custom_fields
    return await _api_create_task(list_id, body)


@mcp.tool
async def update_task(
    task_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    markdown_description: Optional[bool] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assignees: Optional[List[int]] = None,
    tags: Optional[List[str]] = None,
    due_date_ms: Optional[int] = None,
    start_date_ms: Optional[int] = None,
    archived: Optional[bool] = None,
    custom_fields: Optional[List[dict]] = None,
) -> dict:
    """Update a task by id."""
    body: Dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    if markdown_description is not None:
        body["markdown_description"] = bool(markdown_description)
    if status is not None:
        body["status"] = status
    if priority is not None:
        body["priority"] = priority
    if assignees is not None:
        body["assignees"] = assignees
    if tags is not None:
        body["tags"] = tags
    if due_date_ms is not None:
        body["due_date"] = due_date_ms
    if start_date_ms is not None:
        body["start_date"] = start_date_ms
    if archived is not None:
        body["archived"] = bool(archived)
    if custom_fields is not None:
        body["custom_fields"] = custom_fields

    return await client.request("PUT", f"/task/{task_id}", json_body=body)


@mcp.tool
async def delete_task(task_id: str) -> dict:
    """Delete a task by id."""
    return await client.request("DELETE", f"/task/{task_id}")


# -------- Comments (task) --------

@mcp.tool
async def get_task_comments(
    task_id: str,
    start_ms: Optional[int] = None,
    start_id: Optional[str] = None,
) -> dict:
    """
    Get comments for a task (newest first).

    Pagination: pass both `start_ms` and `start_id` to retrieve older comments.
    """
    params = _clean_params({"start": start_ms, "start_id": start_id}) or {}
    return await client.request("GET", f"/task/{task_id}/comment", params=params)


@mcp.tool
async def create_task_comment(
    task_id: str,
    comment_text: str,
    notify_all: bool = False,
    assignee: Optional[int] = None,
) -> dict:
    """
    Create a comment on a task.

    `assignee` is used for "assigned comments" when supported by the workspace.
    """
    body: Dict[str, Any] = {"comment_text": comment_text, "notify_all": bool(notify_all)}
    if assignee is not None:
        body["assignee"] = assignee
    return await client.request("POST", f"/task/{task_id}/comment", json_body=body)


# -------- Search / Activity --------

@mcp.tool
async def search_tasks(
    query: str,
    team_id: Optional[str] = None,
    include_closed: bool = True,
    space_ids: Optional[List[str]] = None,
    list_ids: Optional[List[str]] = None,
    limit: int = 100,
) -> dict:
    """
    Search tasks by name/description.

    Searches across all tasks in the workspace and filters by the query term.
    The search is case-insensitive and matches partial words.

    Args:
        query: Search term to find in task names and descriptions (REQUIRED)
        team_id: Team/workspace ID (uses default if not provided)
        include_closed: Include completed/closed tasks (default: True)
        space_ids: Limit search to specific spaces (optional)
        list_ids: Limit search to specific lists (optional)
        limit: Maximum results to return (default: 100)
    """
    team_id = team_id or await _get_default_team_id()
    query_lower = query.lower()

    # Fetch tasks using ClickUp's filtered endpoint
    params: Dict[str, Any] = {
        "page": 0,
        "include_closed": str(bool(include_closed)).lower(),
        "subtasks": "true",
        "space_ids[]": space_ids,
        "list_ids[]": list_ids,
    }

    all_tasks: List[dict] = []
    page = 0
    max_pages = 10  # Safety limit

    while page < max_pages:
        params["page"] = page
        data = await _api_search_tasks(team_id, params)
        tasks = data.get("tasks", []) if isinstance(data, dict) else []

        if not tasks:
            break

        # Client-side filter: match query in name or description
        for task in tasks:
            name = (task.get("name") or "").lower()
            desc = (task.get("description") or "").lower()
            text_content = (task.get("text_content") or "").lower()

            if query_lower in name or query_lower in desc or query_lower in text_content:
                all_tasks.append(task)
                if len(all_tasks) >= limit:
                    break

        if len(all_tasks) >= limit or len(tasks) < 100:
            break

        page += 1

    return {"tasks": all_tasks[:limit], "query": query, "total_matched": len(all_tasks)}


@mcp.tool
async def filter_tasks(
    team_id: Optional[str] = None,
    space_ids: Optional[List[str]] = None,
    folder_ids: Optional[List[str]] = None,
    list_ids: Optional[List[str]] = None,
    statuses: Optional[List[str]] = None,
    assignees: Optional[List[int]] = None,
    tags: Optional[List[str]] = None,
    due_date_gt_ms: Optional[int] = None,
    due_date_lt_ms: Optional[int] = None,
    date_created_gt_ms: Optional[int] = None,
    date_created_lt_ms: Optional[int] = None,
    date_updated_gt_ms: Optional[int] = None,
    date_updated_lt_ms: Optional[int] = None,
    include_closed: Optional[bool] = None,
    order_by: Optional[str] = "updated",
    most_recent_first: bool = True,
    page: Optional[int] = 0,
    limit: Optional[int] = 50,
) -> dict:
    """
    Filter tasks by various criteria (status, assignee, dates, etc).

    Use search_tasks() for text search. Use this for filtering by metadata.

    Args:
        team_id: Team/workspace ID (uses default if not provided)
        space_ids: Filter by space IDs
        folder_ids: Filter by folder IDs
        list_ids: Filter by list IDs
        statuses: Filter by status names (e.g., ["in progress", "review"])
        assignees: Filter by assignee user IDs
        tags: Filter by tag names
        due_date_gt_ms: Due date after (epoch ms)
        due_date_lt_ms: Due date before (epoch ms)
        date_created_gt_ms: Created after (epoch ms)
        date_created_lt_ms: Created before (epoch ms)
        date_updated_gt_ms: Updated after (epoch ms)
        date_updated_lt_ms: Updated before (epoch ms)
        include_closed: Include closed tasks
        order_by: Sort field (updated, created, due_date)
        most_recent_first: Sort newest first (default: True)
        page: Page number
        limit: Max results (default: 50)
    """
    team_id = team_id or await _get_default_team_id()

    clickup_reverse = "false" if most_recent_first else "true"

    params: Dict[str, Any] = {
        "page": page,
        "order_by": order_by,
        "reverse": clickup_reverse,
        "include_closed": str(bool(include_closed)).lower() if include_closed is not None else None,
        "limit": limit,
        "space_ids[]": space_ids,
        "folder_ids[]": folder_ids,
        "list_ids[]": list_ids,
        "statuses[]": statuses,
        "assignees[]": assignees,
        "tags[]": tags,
        "due_date_gt": due_date_gt_ms,
        "due_date_lt": due_date_lt_ms,
        "date_created_gt": date_created_gt_ms,
        "date_created_lt": date_created_lt_ms,
        "date_updated_gt": date_updated_gt_ms,
        "date_updated_lt": date_updated_lt_ms,
    }

    data = await _api_search_tasks(team_id, params)
    # ClickUp often returns up to 100 tasks per page regardless; enforce `limit` client-side.
    if isinstance(data, dict) and isinstance(data.get("tasks"), list) and isinstance(limit, int) and limit > 0:
        data["tasks"] = data["tasks"][:limit]
    return data


@mcp.tool
async def recent_activity(
    team_id: Optional[str] = None,
    since_ms: Optional[int] = None,
    query: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """
    "Recent activity" helper.

    Prefer ClickUp audit logs when available; otherwise falls back to "recently updated tasks" search.
    """
    team_id = team_id or await _get_default_team_id()
    since_ms = since_ms or (_now_ms() - 7 * 24 * 60 * 60 * 1000)

    # 1) Try audit logs (enterprise-only for some accounts)
    try:
        audit = await client.request(
            "GET",
            f"/team/{team_id}/audit",
            params=_clean_params({"start_date": since_ms, "limit": limit, "query": query}),
        )
        return {"source": "audit", "data": audit}
    except ClickUpAPIError as e:
        # 2) Fallback: updated tasks
        tasks = await _api_search_tasks(
            team_id,
            {
                "page": 0,
                "order_by": "updated",
                # Newest-first
                "reverse": "false",
                "include_closed": "true",
                "limit": limit,
                "query": query,
                "date_updated_gt": since_ms,
            },
        )
        return {"source": "updated_tasks", "audit_error": {"status": e.status_code, "details": e.details}, "data": tasks}


# -------- Generic escape hatch --------

@mcp.tool
async def clickup_api_request(
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"],
    path: str,
    query_params: Optional[Dict[str, Any]] = None,
    json_body: Any | None = None,
) -> Any:
    """
    Call any ClickUp API endpoint (escape hatch for new/rare endpoints).

    `path` must be an API path like `/task/{id}` (no scheme/host).
    """
    if "://" in path:
        raise RuntimeError("path must be a relative API path (no scheme/host)")
    if ".." in path:
        raise RuntimeError("path must not contain '..'")
    return await client.request(method, path, params=_clean_params(query_params), json_body=json_body)


# -------- Docs (v3 API) --------

@mcp.tool
async def search_docs(
    workspace_id: Optional[str] = None,
) -> dict:
    """
    Search/list all Docs in the workspace (v3 API).

    Returns metadata for all Docs you can access.

    Args:
        workspace_id: Workspace ID (uses default if not provided)
    """
    workspace_id = workspace_id or await _get_default_workspace_id()
    return await client_v3.request("GET", f"/workspaces/{workspace_id}/docs")


@mcp.tool
async def get_doc(
    doc_id: str,
    workspace_id: Optional[str] = None,
) -> dict:
    """
    Get a Doc by ID (v3 API).

    Returns doc metadata including list of pages.

    Args:
        doc_id: The Doc ID
        workspace_id: Workspace ID (uses default if not provided)
    """
    workspace_id = workspace_id or await _get_default_workspace_id()
    return await client_v3.request("GET", f"/workspaces/{workspace_id}/docs/{doc_id}")


@mcp.tool
async def create_doc(
    name: str,
    workspace_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    parent_type: Optional[Literal["space", "folder", "list", "doc"]] = None,
    visibility: Optional[Literal["private", "workspace"]] = None,
) -> dict:
    """
    Create a new Doc (v3 API).

    Args:
        name: Doc name/title
        workspace_id: Workspace ID (uses default if not provided)
        parent_id: Optional parent container ID (space, folder, list, or doc)
        parent_type: Type of parent container
        visibility: Doc visibility (private or workspace)
    """
    workspace_id = workspace_id or await _get_default_workspace_id()
    body: Dict[str, Any] = {"name": name}
    if parent_id is not None:
        body["parent"] = {"id": parent_id, "type": parent_type or "space"}
    if visibility is not None:
        body["visibility"] = visibility
    return await client_v3.request("POST", f"/workspaces/{workspace_id}/docs", json_body=body)


# -------- Pages (v3 API) --------

@mcp.tool
async def list_doc_pages(
    doc_id: str,
    workspace_id: Optional[str] = None,
) -> dict:
    """
    List all pages in a Doc (v3 API).

    Args:
        doc_id: The Doc ID
        workspace_id: Workspace ID (uses default if not provided)
    """
    workspace_id = workspace_id or await _get_default_workspace_id()
    return await client_v3.request("GET", f"/workspaces/{workspace_id}/docs/{doc_id}/pages")


@mcp.tool
async def get_doc_page_listing(
    doc_id: str,
    workspace_id: Optional[str] = None,
) -> dict:
    """
    Get hierarchical page listing for a Doc (v3 API).

    Returns the page structure/tree for the Doc.

    Args:
        doc_id: The Doc ID
        workspace_id: Workspace ID (uses default if not provided)
    """
    workspace_id = workspace_id or await _get_default_workspace_id()
    return await client_v3.request("GET", f"/workspaces/{workspace_id}/docs/{doc_id}/page_listing")


@mcp.tool
async def get_doc_page(
    doc_id: str,
    page_id: str,
    workspace_id: Optional[str] = None,
) -> dict:
    """
    Get a specific page from a Doc (v3 API).

    Returns page content. Note: due to markdown format limitations,
    some content elements may not appear exactly as in ClickUp.

    Args:
        doc_id: The Doc ID
        page_id: The Page ID
        workspace_id: Workspace ID (uses default if not provided)
    """
    workspace_id = workspace_id or await _get_default_workspace_id()
    return await client_v3.request("GET", f"/workspaces/{workspace_id}/docs/{doc_id}/pages/{page_id}")


@mcp.tool
async def create_doc_page(
    doc_id: str,
    name: str,
    content: Optional[str] = None,
    parent_page_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    content_format: Literal["text/md", "text/plain"] = "text/md",
) -> dict:
    """
    Create a new page in a Doc (v3 API).

    Args:
        doc_id: The Doc ID
        name: Page title
        content: Page content (markdown or plaintext)
        parent_page_id: Optional parent page ID for nested pages
        workspace_id: Workspace ID (uses default if not provided)
        content_format: Content format - "text/md" (markdown) or "text/plain"
    """
    workspace_id = workspace_id or await _get_default_workspace_id()
    body: Dict[str, Any] = {"name": name}
    if content is not None:
        body["content"] = content
        body["content_format"] = content_format
    if parent_page_id is not None:
        body["parent_page_id"] = parent_page_id
    return await client_v3.request("POST", f"/workspaces/{workspace_id}/docs/{doc_id}/pages", json_body=body)


@mcp.tool
async def update_doc_page(
    doc_id: str,
    page_id: str,
    name: Optional[str] = None,
    content: Optional[str] = None,
    workspace_id: Optional[str] = None,
    content_format: Literal["text/md", "text/plain"] = "text/md",
    content_edit_mode: Literal["replace", "append", "prepend"] = "replace",
) -> dict:
    """
    Update/edit a page in a Doc (v3 API).

    Args:
        doc_id: The Doc ID
        page_id: The Page ID
        name: New page title (optional)
        content: New page content (optional)
        workspace_id: Workspace ID (uses default if not provided)
        content_format: Content format - "text/md" (markdown) or "text/plain"
        content_edit_mode: How to apply content - "replace", "append", or "prepend"
    """
    workspace_id = workspace_id or await _get_default_workspace_id()
    body: Dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if content is not None:
        body["content"] = content
        body["content_format"] = content_format
        body["content_edit_mode"] = content_edit_mode
    return await client_v3.request("PUT", f"/workspaces/{workspace_id}/docs/{doc_id}/pages/{page_id}", json_body=body)


# -------- Generic v3 escape hatch --------

@mcp.tool
async def clickup_v3_api_request(
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"],
    path: str,
    query_params: Optional[Dict[str, Any]] = None,
    json_body: Any | None = None,
) -> Any:
    """
    Call any ClickUp v3 API endpoint (escape hatch for new/rare endpoints).

    `path` must be a v3 API path like `/workspaces/{id}/docs` (no scheme/host, no /api/v3 prefix).
    """
    if "://" in path:
        raise RuntimeError("path must be a relative API path (no scheme/host)")
    if ".." in path:
        raise RuntimeError("path must not contain '..'")
    return await client_v3.request(method, path, params=_clean_params(query_params), json_body=json_body)


@mcp.tool
async def health() -> dict:
    """Simple health check (does not call ClickUp)."""
    return {"ok": True}
