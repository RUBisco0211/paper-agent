"""The single chat entry: plain messages plus server-validated references.

Upstream exposes ``POST /chat/`` for a ready-made message. References must be
checked against the session scope *before* the model sees them, so this module
takes that route over: same path, same execution path, plus optional
``references`` and ``mentions``. With neither field the request is handed to
the upstream handler unchanged.
"""

from functools import lru_cache
from typing import Annotated, Any

import httpx
from agentscope.app._manager import ChatRunRegistry
from agentscope.app._router._chat import chat as upstream_chat
from agentscope.app._router._chat import chat_router
from agentscope.app._router._schema import ChatRequest, ChatTriggerResponse
from agentscope.app._service import ChatService
from agentscope.app.deps import (
    get_chat_run_registry,
    get_chat_service,
    get_current_user_id,
    get_message_bus,
    get_storage,
)
from agentscope.app.message_bus import MessageBus
from agentscope.app.storage import StorageBase
from agentscope.message import Base64Source, DataBlock, TextBlock, UserMsg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from .quoted_chat import (
    MessageQuote,
    PaperMention,
    PaperQuote,
    Quote,
    apply_mentions,
    image_model_unavailable,
    render_quoted_content,
    validate_message_quote,
)
from .tools.request import business_request

router = APIRouter(prefix="/chat", tags=["chat"])
UserId = Annotated[str, Depends(get_current_user_id)]
StorageDep = Annotated[StorageBase, Depends(get_storage)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
RegistryDep = Annotated[ChatRunRegistry, Depends(get_chat_run_registry)]
MessageBusDep = Annotated[MessageBus, Depends(get_message_bus)]


class ChatEntryRequest(ChatRequest):
    """The upstream body plus the two optional reference fields."""

    # Reference-only sends carry no ready-made message.
    input: Any = None
    text: str = Field(default="", max_length=20000)
    references: list[Quote] = Field(default_factory=list, max_length=8)
    mentions: list[PaperMention] = Field(default_factory=list, max_length=50)


@lru_cache(maxsize=1)
def take_over_chat_route() -> None:
    """Drop the built-in ``POST /chat/`` before the app includes the router.

    Called once from ``create_agent_service_app``; the module-level router in
    the dependency stays untouched, so nothing under ``site-packages`` is
    edited and a reload rebuilds the same state.
    """
    chat_router.routes[:] = [
        route for route in chat_router.routes if route.name != "chat"
    ]


@router.post("/", response_model=ChatTriggerResponse)
async def chat(
    request: ChatEntryRequest,
    user_id: UserId,
    storage: StorageDep,
    chat_service: ChatServiceDep,
    registry: RegistryDep,
    message_bus: MessageBusDep,
) -> ChatTriggerResponse:
    if not request.references and not request.mentions:
        return await upstream_chat(
            request=ChatRequest(
                agent_id=request.agent_id,
                session_id=request.session_id,
                input=request.input,
            ),
            user_id=user_id,
            chat_service=chat_service,
            chat_run_registry=registry,
            message_bus=message_bus,
        )

    session = await storage.get_session(
        user_id, request.agent_id, request.session_id
    )
    if (
        session is None
        or session.user_id != user_id
        or session.agent_id != request.agent_id
    ):
        raise HTTPException(404, "session_not_found")
    if any(
        isinstance(ref, PaperQuote) and ref.include_image
        for ref in request.references
    ):
        model = session.config.chat_model_config
        if image_model_unavailable(model.type if model else None):
            raise HTTPException(
                422, "当前模型不支持图片，请切换支持图片输入的模型后重试"
            )
    image_blocks: list[DataBlock] = []
    for ref in request.references:
        try:
            if isinstance(ref, MessageQuote):
                source = await storage.get_message(
                    user_id, request.session_id, ref.source_message_id
                )
                validate_message_quote(source, ref)
                continue
            resolved = await business_request(
                "POST",
                "quote-reference/resolve",
                json={
                    "user_id": user_id,
                    "session_id": request.session_id,
                    **ref.model_dump(exclude={"source_title"}),
                },
            )
            ref.source_title = resolved.get("title")
            if ref.include_image:
                if (
                    not resolved.get("image_base64")
                    or not resolved.get("image_media_type")
                ):
                    raise ValueError("image_unavailable")
                image_blocks.append(
                    DataBlock(
                        source=Base64Source(
                            data=resolved["image_base64"],
                            media_type=resolved["image_media_type"],
                        )
                    )
                )
        except ValueError as exc:
            raise HTTPException(
                422, "引用的消息已不可用，请重新选择后发送"
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = 422 if exc.response.status_code == 422 else 404
            detail = (
                "文献内容已更新，请重新选择引用"
                if status_code == 422
                else "引用文献已不可用或不在当前会话范围"
            )
            raise HTTPException(status_code, detail) from exc
        except httpx.RequestError as exc:
            raise HTTPException(503, "引用文献暂时无法核验，请稍后重试") from exc

    resolved_mentions: dict[int, dict] = {}
    for mention in request.mentions:
        try:
            resolved = await business_request(
                "POST",
                "quote-reference/resolve",
                json={
                    "user_id": user_id,
                    "session_id": request.session_id,
                    "kind": "paper",
                    "user_paper_id": mention.user_paper_id,
                    "selected_text": "",
                    "comment": "",
                },
            )
        except httpx.HTTPStatusError as exc:
            status_code = 422 if exc.response.status_code == 422 else 404
            raise HTTPException(
                status_code, "引用的文献已不可用或不在当前会话范围"
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                503, "引用文献暂时无法核验，请稍后重试"
            ) from exc
        resolved_mentions[mention.index] = {
            "title": resolved.get("title"),
            "has_fulltext": bool(resolved.get("has_fulltext")),
            "user_paper_id": mention.user_paper_id,
        }

    rendered_text = apply_mentions(request.text, resolved_mentions)
    message = UserMsg(
        "user",
        [
            TextBlock(text=render_quoted_content(rendered_text, request.references)),
            *image_blocks,
        ],
        metadata={
            "paper_agent": {
                "body": rendered_text,
                "references": [ref.model_dump() for ref in request.references],
                "mentions": [
                    {
                        "index": index,
                        "user_paper_id": resolved["user_paper_id"],
                        "title": resolved["title"],
                        "has_fulltext": resolved["has_fulltext"],
                    }
                    for index, resolved in sorted(resolved_mentions.items())
                ],
            }
        },
    )
    try:
        registry.spawn(
            chat_service.run(
                user_id=user_id,
                session_id=request.session_id,
                agent_id=request.agent_id,
                input_msg=message,
            ),
            session_id=request.session_id,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return ChatTriggerResponse(
        status="started",
        session_id=request.session_id,
        message_id=message.id,
    )
