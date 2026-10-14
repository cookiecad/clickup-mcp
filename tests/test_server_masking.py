"""Exercise the MCP serialization boundary using only synthetic HTTP responses."""
import json
import os

os.environ["CLICKUP_API_TOKEN"] = "synthetic-test-token"
os.environ["CLICKUP_TEAM_ID"] = "1"
os.environ["CLICKUP_WORKSPACE_ID"] = "1"

import httpx
import pytest
from fastmcp import Client

from clickup_mcp import server
from clickup_mcp.clickup_api import ClickUpAPIError, ClickUpClient, ClickUpV3Client
from clickup_mcp.redact import MASK, RULES_VERSION

SECRETS = ["7391", "Tr0ub4dor-3", "448812", "synthetic-url-key", "synthetic-doc-key"]
TASK = {
    "id": "synthetic-task", "name": "Portal login follow-up", "status": {"status": "Open"},
    "url": "https://app.clickup.com/t/synthetic-task", "assignees": [{"id": 42}],
    "description": "Portal login. PIN: 7391, password: Tr0ub4dor-3",
    "text_content": "Portal PIN:\n7391", "markdown_description": "**PIN:** 7391",
    "custom_fields": [{"name": "Portal PIN", "value": "7391"}],
    "subtasks": [{"id": "synthetic-subtask", "description": "PIN is 7391"}],
}


def handler(request):
    assert request.method == "GET"
    path = request.url.path
    if path.endswith("/comment"):
        data = {"comments": [{"comment_text": "temporary passcode 448812, link https://files.example.com/d/abc#keyCode=synthetic-url-key",
                              "comment": [{"text": "PIN - 7391"}]}]}
    elif "/docs/" in path:
        data = {"id": "synthetic-page", "content": "api key = synthetic-doc-key"}
    elif "/team/" in path or "/list/" in path:
        data = {"tasks": [TASK]}
    else:
        data = TASK
    return httpx.Response(200, json=data)


@pytest.fixture
async def mocked_server(monkeypatch):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://synthetic.invalid/api/v2") as v2:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://synthetic.invalid/api/v3") as v3:
            monkeypatch.setattr(server.client, "_client", v2)
            monkeypatch.setattr(server.client_v3, "_client", v3)
            yield


@pytest.mark.parametrize("tool,args", [
    ("get_task", {"task_id": "synthetic-task", "include_subtasks": True}),
    ("get_task_comments", {"task_id": "synthetic-task"}),
    ("search_tasks", {"query": "Portal"}),
    ("filter_tasks", {"team_id": "1"}),
    ("list_tasks_in_list", {"list_id": "synthetic-list"}),
    ("get_doc_page", {"doc_id": "synthetic-doc", "page_id": "synthetic-page"}),
    ("clickup_api_request", {"method": "GET", "path": "/task/synthetic-task"}),
    ("clickup_v3_api_request", {"method": "GET", "path": "/workspaces/1/docs/synthetic-doc/pages/synthetic-page"}),
])
async def test_tool_output_is_masked_before_serialization(mocked_server, tool, args):
    async with Client(server.mcp) as client:
        result = await client.call_tool(tool, args)
    output = json.dumps([part.model_dump() for part in result.content])
    assert MASK in output
    for secret in SECRETS:
        assert secret not in output
    if "synthetic-task" in output:
        assert "Portal login follow-up" in output
        assert "https://app.clickup.com/t/synthetic-task" in output
        assert "Open" in output
        assert "42" in output


async def test_search_cannot_recover_masked_pin_and_health_is_local(mocked_server):
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_tasks", {"query": "7391"})
        assert result.data["tasks"] == []
        health = await client.call_tool("health", {})
        assert health.data == {"ok": True, "credential_masking": RULES_VERSION}


@pytest.mark.parametrize("client_type", [ClickUpClient, ClickUpV3Client])
@pytest.mark.parametrize("body,json_body", [("PIN: 7391", False), ({"err": "PIN: 7391", "message": "password: Tr0ub4dor-3"}, True)])
async def test_remote_error_text_and_details_are_masked(client_type, body, json_body):
    def error_handler(request):
        return httpx.Response(400, **({"json": body} if json_body else {"text": body}))
    client = client_type(api_token="synthetic-test-token", base_url="https://synthetic.invalid")
    await client.aclose()
    async with httpx.AsyncClient(transport=httpx.MockTransport(error_handler), base_url="https://synthetic.invalid") as transport:
        client._client = transport
        with pytest.raises(ClickUpAPIError) as raised:
            await client.request("GET", "/task/synthetic-task")
        output = str(raised.value) + json.dumps(raised.value.details)
        assert "7391" not in output
        assert "Tr0ub4dor-3" not in output
        assert MASK in output


@pytest.mark.parametrize("client_type", [ClickUpClient, ClickUpV3Client])
async def test_debug_and_transport_errors_do_not_echo_credentials(client_type, capsys):
    def fail(request):
        raise httpx.ConnectError("PIN: 7391", request=request)
    client = client_type(api_token="synthetic-test-token", base_url="https://synthetic.invalid", debug_http=True)
    await client.aclose()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fail), base_url="https://synthetic.invalid") as transport:
        client._client = transport
        with pytest.raises(ClickUpAPIError) as raised:
            await client.request("GET", "/task/synthetic-task", params={"PIN": "7391"}, json_body={"description": "password: Tr0ub4dor-3"})
        output = capsys.readouterr().out + str(raised.value)
        assert "7391" not in output
        assert "Tr0ub4dor-3" not in output
        assert MASK in output
