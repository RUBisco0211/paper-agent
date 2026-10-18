"""Automatic session naming from the first user prompt."""

from pathlib import Path

import pytest
from agentscope.message import TextBlock
from agentscope.model import ChatResponse
from fastapi.testclient import TestClient

from agent_service import session_name
from agent_service.main import create_agent_service_app
from tests.agent_service.test_auth import _scope_database_url


class _FakeNamingModel:
    stream = True

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[list] = []

    async def __call__(self, messages, tools=None, tool_choice=None, **kwargs):
        self.calls.append(messages)
        return ChatResponse(content=[TextBlock(text=self.reply)], is_last=True)


class _FailingNamingModel:
    stream = True

    async def __call__(self, messages, tools=None, tool_choice=None, **kwargs):
        raise RuntimeError("provider details must not reach the browser")


def _create_session(
    client: TestClient,
    headers: dict[str, str],
    *,
    name: str | None = None,
) -> tuple[str, str]:
    credential = client.post(
        "/credential/",
        headers=headers,
        json={"data": {"type": "openai_credential", "api_key": "sk-test"}},
    )
    assert credential.status_code == 201, credential.text
    agent = client.post("/agent/", headers=headers, json={"name": "Reader"})
    assert agent.status_code == 201, agent.text
    agent_id = agent.json()["agent_id"]
    session_body = {
        "agent_id": agent_id,
        "chat_model_config": {
            "type": "openai_credential",
            "credential_id": credential.json()["credential_id"],
            "model": "gpt-test",
            "parameters": {},
        },
    }
    if name is not None:
        session_body["name"] = name
    session = client.post("/sessions/", headers=headers, json=session_body)
    assert session.status_code == 201, session.text
    return agent_id, session.json()["session_id"]


def _use_model(monkeypatch: pytest.MonkeyPatch, model) -> None:
    async def fake_get_model(*args):
        return model

    monkeypatch.setattr(session_name, "get_model", fake_get_model)


def _session_name(
    client: TestClient, headers: dict[str, str], agent_id: str, session_id: str
) -> str:
    sessions = client.get(
        "/sessions/",
        params={"agent_id": agent_id},
        headers=headers,
    ).json()["sessions"]
    return next(
        view["session"]["config"]["name"]
        for view in sessions
        if view["session"]["id"] == session_id
    )


def test_session_naming_uses_the_session_model_and_persists_the_cleaned_title(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent_access_token: str,
) -> None:
    fake = _FakeNamingModel("“RAG 方法比较。”")
    _use_model(monkeypatch, fake)
    app = create_agent_service_app(_scope_database_url(), tmp_path)
    headers = {"Authorization": f"Bearer {agent_access_token}"}

    with TestClient(app) as client:
        agent_id, session_id = _create_session(client, headers)
        response = client.post(
            f"/sessions/{session_id}/name",
            headers=headers,
            json={
                "agent_id": agent_id,
                "text": "比较这两篇文献",
                "excerpts": ["检索增强生成的局限\n评论：关注召回率"],
                "project_name": "RAG 综述",
                "project_description": "关注 2023 年后的检索增强生成方法",
            },
        )

        assert response.status_code == 200, response.text
        assert response.json() == {"name": "RAG 方法比较"}
        assert _session_name(client, headers, agent_id, session_id) == "RAG 方法比较"

    assert len(fake.calls) == 1
    system, user = fake.calls[0]
    assert system.role == "system"
    assert "只输出标题本身" in system.content[0].text
    prompt = user.content[0].text
    assert "名称：RAG 综述" in prompt
    assert "简介：关注 2023 年后的检索增强生成方法" in prompt
    assert "<user_prompt>\n比较这两篇文献\n</user_prompt>" in prompt
    assert "<referenced_excerpts>" in prompt
    assert "检索增强生成的局限\n评论：关注召回率" in prompt


def test_session_naming_accepts_a_reference_only_first_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent_access_token: str,
) -> None:
    fake = _FakeNamingModel("检索增强生成的局限")
    _use_model(monkeypatch, fake)
    app = create_agent_service_app(_scope_database_url(), tmp_path)
    headers = {"Authorization": f"Bearer {agent_access_token}"}

    with TestClient(app) as client:
        agent_id, session_id = _create_session(client, headers)
        response = client.post(
            f"/sessions/{session_id}/name",
            headers=headers,
            json={
                "agent_id": agent_id,
                "text": "",
                "excerpts": ["检索增强生成的局限"],
                "project_name": "RAG 综述",
            },
        )

        assert response.status_code == 200, response.text
        assert response.json() == {"name": "检索增强生成的局限"}

    prompt = fake.calls[0][1].content[0].text
    assert "<user_prompt>" not in prompt
    assert "<project>\n名称：RAG 综述\n</project>" in prompt
    assert "1. 检索增强生成的局限" in prompt


def test_session_naming_rejects_empty_input_without_calling_the_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent_access_token: str,
) -> None:
    fake = _FakeNamingModel("不会被调用")
    _use_model(monkeypatch, fake)
    app = create_agent_service_app(_scope_database_url(), tmp_path)
    headers = {"Authorization": f"Bearer {agent_access_token}"}

    with TestClient(app) as client:
        agent_id, session_id = _create_session(client, headers)
        response = client.post(
            f"/sessions/{session_id}/name",
            headers=headers,
            json={"agent_id": agent_id, "text": "  ", "excerpts": []},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "empty_session_name_input"
    assert fake.calls == []


def test_session_naming_does_not_overwrite_a_manual_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent_access_token: str,
) -> None:
    fake = _FakeNamingModel("自动标题")
    _use_model(monkeypatch, fake)
    app = create_agent_service_app(_scope_database_url(), tmp_path)
    headers = {"Authorization": f"Bearer {agent_access_token}"}

    with TestClient(app) as client:
        agent_id, session_id = _create_session(client, headers, name="手动标题")
        response = client.post(
            f"/sessions/{session_id}/name",
            headers=headers,
            json={"agent_id": agent_id, "text": "比较这两篇文献"},
        )

        assert response.status_code == 200, response.text
        assert response.json() == {"name": "手动标题"}
        assert _session_name(client, headers, agent_id, session_id) == "手动标题"

    assert fake.calls == []


def test_session_naming_failure_keeps_the_previous_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent_access_token: str,
) -> None:
    _use_model(monkeypatch, _FailingNamingModel())
    app = create_agent_service_app(_scope_database_url(), tmp_path)
    headers = {"Authorization": f"Bearer {agent_access_token}"}

    with TestClient(app) as client:
        agent_id, session_id = _create_session(client, headers)
        before = _session_name(client, headers, agent_id, session_id)
        response = client.post(
            f"/sessions/{session_id}/name",
            headers=headers,
            json={"agent_id": agent_id, "text": "比较这两篇文献"},
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "session_name_unavailable"
        assert _session_name(client, headers, agent_id, session_id) == before


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("“RAG 方法比较。”", "RAG 方法比较"),
        ("标题：文献综述\n", "文献综述"),
        ("Session title: RAG comparison", "RAG comparison"),
        ("  \n ", ""),
    ],
)
def test_generated_session_name_is_cleaned(raw: str, expected: str) -> None:
    assert session_name.clean_generated_name(raw) == expected
