# ClickUp MCP (Streamable HTTP)

MCP server for ClickUp's REST API with:
- Workspace-wide task search (`GET /team/{team_id}/task`)
- Task CRUD (+ subtasks)
- Basic browsing (teams, spaces, folders, lists)
- Recent activity helpers (via `date_updated_gt`, plus audit logs when available)
- **Docs CRUD/search** (v3 API): search, get, create Docs and Pages
- Escape hatch: generic tool to call any ClickUp API endpoint (v2 and v3).

This server is intended to run as a Docker service and be consumed by OpenWebUI and LibreChat.

## Environment

- `CLICKUP_API_TOKEN` (required)
- `CLICKUP_TEAM_ID` (optional, will auto-detect first team if unset)
- `CLICKUP_WORKSPACE_ID` (optional; ClickUp often calls this "team_id" in v2)
- `CLICKUP_API_BASE_URL` (optional, default `https://api.clickup.com/api/v2`)
- `CLICKUP_API_V3_BASE_URL` (optional, default `https://api.clickup.com/api/v3`)

## Run (local)

```bash
python -m clickup_mcp --transport streamable-http --host 0.0.0.0 --port 8000 --path /mcp
```

OpenWebUI should connect to: `http://clickup-mcp:8000/mcp`

## Tools

### Tasks (v2 API)
- `search_tasks` - Search tasks by name/description
- `filter_tasks` - Filter tasks by metadata (status, assignee, dates, etc.)
- `get_task` - Get a task by ID
- `create_task` - Create a new task
- `create_subtask` - Create a subtask under an existing task
- `update_task` - Update a task
- `delete_task` - Delete a task
- `get_task_comments` - Get comments for a task
- `create_task_comment` - Create a comment on a task

### Browsing (v2 API)
- `clickup_context` - Get resolved context (team/workspace ID and current user)
- `list_teams` - List ClickUp teams/workspaces
- `get_team` - Get a team by ID
- `list_spaces` - List spaces in a team
- `list_folders` - List folders in a space
- `list_lists_in_space` - List (folderless) lists in a space
- `list_lists_in_folder` - List lists in a folder
- `list_tasks_in_list` - List tasks in a list

### Docs (v3 API)
- `search_docs` - Search/list all Docs in the workspace
- `get_doc` - Get a Doc by ID (includes page list)
- `create_doc` - Create a new Doc

### Pages (v3 API)
- `list_doc_pages` - List all pages in a Doc
- `get_doc_page_listing` - Get hierarchical page structure for a Doc
- `get_doc_page` - Get a specific page (with content)
- `create_doc_page` - Create a new page in a Doc
- `update_doc_page` - Update/edit a page (replace, append, or prepend content)

### Utility
- `recent_activity` - Get recent activity (audit logs or recently updated tasks)
- `clickup_api_request` - Generic v2 API escape hatch
- `clickup_v3_api_request` - Generic v3 API escape hatch
- `health` - Health check

