import os


def getenv_str(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip()
    return v if v else default


def getenv_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


class Settings:
    def __init__(self) -> None:
        self.api_token = getenv_str("CLICKUP_API_TOKEN")
        self.api_base_url = getenv_str("CLICKUP_API_BASE_URL", "https://api.clickup.com/api/v2")
        self.api_v3_base_url = getenv_str("CLICKUP_API_V3_BASE_URL", "https://api.clickup.com/api/v3")

        # In ClickUp's v2 API, the workspace is called "team". Many docs use team_id for workspace id.
        # In v3 API, it's consistently called "workspace_id".
        self.team_id = getenv_str("CLICKUP_TEAM_ID") or getenv_str("CLICKUP_WORKSPACE_ID")
        self.workspace_id = self.team_id  # Alias for v3 API compatibility

        # Optional: if set, require `Authorization: Bearer <token>` from MCP clients.
        self.mcp_auth_token = getenv_str("CLICKUP_MCP_AUTH_TOKEN")

        # Optional: enable verbose logging of upstream requests (without headers).
        self.debug_http = getenv_bool("CLICKUP_MCP_DEBUG_HTTP", False)

    def validate(self) -> None:
        if not self.api_token:
            raise RuntimeError("CLICKUP_API_TOKEN is required")

