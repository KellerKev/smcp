"""A reply is the answer to the request just sent: fresh, new, and naming that request.

The signature on a reply says the server made it at some point. Without these checks somebody
between client and server could answer a call with an earlier (validly signed) reply — stale
file content, say — and the client would take it.
"""
import asyncio
import json
import secrets
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smcp_client import SMCPClient
from smcp_config import SMCPConfig
from smcp_core import MessageType, SMCPMessage, SMCPNode


def _pair():
    kw = dict(api_key=secrets.token_urlsafe(32), secret_key=secrets.token_urlsafe(32),
              jwt_secret=secrets.token_urlsafe(32), kdf_salt=secrets.token_urlsafe(16))
    client = SMCPClient(SMCPConfig(node_id="cli", **kw))
    server = SMCPNode("srv", kw["secret_key"], kw["jwt_secret"], kw["kdf_salt"],
                      api_key=kw["api_key"])
    return client, server


class _Wire:
    """A websocket that answers with whatever `answer` returns for the request sent."""

    def __init__(self, answer):
        self.answer, self.sent = answer, None

    async def send(self, raw):
        self.sent = json.loads(raw)

    async def recv(self):
        return json.dumps(self.answer(self.sent))


def _serve(server):
    return lambda request: server.process_message(SMCPMessage.from_dict(request)).to_dict()


def test_every_answer_names_the_request_it_answers():
    client, server = _pair()
    request = client.node.create_message(MessageType.HANDSHAKE, {
        "client_id": "cli", "protocol_version": "3.0", "nonce": "n" * 32}, encrypt=False)
    reply = server.process_message(SMCPMessage.from_dict(request.to_dict()))
    payload = reply.payload
    if reply.encrypted and "encrypted_data" in payload:
        payload = server.security.decrypt_payload(payload["encrypted_data"])
    assert payload["request_id"] == request.id


def test_the_client_takes_the_answer_to_its_own_request_only():
    client, server = _pair()
    first = client.node.create_message(MessageType.HANDSHAKE, {
        "client_id": "cli", "protocol_version": "3.0", "nonce": "a" * 32}, encrypt=False)
    client.websocket = _Wire(_serve(server))
    answer_to_first = asyncio.run(client._send_message(first))        # the honest exchange
    assert answer_to_first["type"] == "handshake"

    # the same reply again: somebody recorded it and plays it back
    second = client.node.create_message(MessageType.HANDSHAKE, {
        "client_id": "cli", "protocol_version": "3.0", "nonce": "b" * 32}, encrypt=False)
    client.websocket = _Wire(lambda request: answer_to_first)
    with pytest.raises(Exception, match="stale or was already received"):
        asyncio.run(client._send_message(second))

    # a fresh reply — but to another request (two calls in flight, answers swapped)
    other = client.node.create_message(MessageType.HANDSHAKE, {
        "client_id": "cli", "protocol_version": "3.0", "nonce": "c" * 32}, encrypt=False)
    swapped = server.process_message(SMCPMessage.from_dict(other.to_dict())).to_dict()
    third = client.node.create_message(MessageType.HANDSHAKE, {
        "client_id": "cli", "protocol_version": "3.0", "nonce": "d" * 32}, encrypt=False)
    client.websocket = _Wire(lambda request: swapped)
    with pytest.raises(Exception, match="answers another request"):
        asyncio.run(client._send_message(third))


def test_a_tool_call_takes_a_tool_response_for_that_tool():
    client, server = _pair()
    client.connected, client.auth_token = True, "t"

    def reply_for(tool):
        return lambda request: server.create_message(MessageType.TOOL_RESPONSE, {
            "tool_name": tool, "result": "content of " + tool, "status": "success",
            "request_id": request["id"]}).to_dict()
    client.websocket = _Wire(reply_for("read_file"))
    assert asyncio.run(client.invoke_tool("read_file", path="x")) == "content of read_file"
    client.websocket = _Wire(reply_for("list_directory"))
    with pytest.raises(Exception, match="not 'read_file'"):
        asyncio.run(client.invoke_tool("read_file", path="x"))
    client.websocket = _Wire(lambda request: server.create_message(
        MessageType.CAPABILITY_DISCOVERY, {"capabilities": {}, "request_id": request["id"]}).to_dict())
    with pytest.raises(Exception, match="unexpected"):
        asyncio.run(client.invoke_tool("read_file", path="x"))
