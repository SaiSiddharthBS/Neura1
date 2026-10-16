import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from neura1 import main
from neura1.config import settings
from neura1.webhooks import verify_slack


@pytest.fixture
def client(fresh_graph):
    main.app.dependency_overrides[main.graph] = lambda: fresh_graph
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_slack_message_becomes_a_linked_passage(client, fresh_graph):
    secret = {"x-neura1-webhook-secret": settings.webhook_secret}
    assert client.post("/api/webhooks/slack", json={"type": "url_verification", "challenge": "abc"},
                       headers=secret).json() == {"challenge": "abc"}
    assert client.post("/api/webhooks/slack", json={}).status_code == 401
    r = client.post("/api/webhooks/slack", headers=secret, json={"type": "event_callback", "event": {
        "type": "message", "channel_name": "fw-team", "user_profile": {"real_name": "Vinay"},
        "text": "Bus-off recovery for CT-1051 is on the bench; works across 20 cold starts.", "ts": "1760600000.0001"}}).json()
    linked = fresh_graph.ro_query("MATCH (c:Chunk {id:$id})-[:MENTIONS]->(x) RETURN x.id", {"id": r["ingested"]}).result_set
    said = fresh_graph.ro_query("MATCH (c:Chunk {id:$id})-[:SAID_BY]->(p) RETURN p.name", {"id": r["ingested"]}).result_set
    assert ["CT-1051"] in linked and said == [["Vinay"]]


def test_jira_comment_updates_ticket_and_assignee(client, fresh_graph):
    secret = {"x-neura1-webhook-secret": settings.webhook_secret}
    r = client.post("/api/webhooks/jira", headers=secret, json={
        "webhookEvent": "comment_created",
        "issue": {"key": "SUP-1060", "fields": {"summary": "BCU-24 charger fan noise", "status": {"name": "In Progress"},
                                                "assignee": {"displayName": "Nagarjun"}, "description": "Fan noise on BCU-24 Rev A."}},
        "comment": {"id": "9", "author": {"displayName": "Yogish"}, "body": "Reproduced at 55C.", "created": "2026-10-16T10:00:00"}}).json()
    assert len(r["ingested"]) == 2 and r["status"] == "In Progress"
    who = fresh_graph.ro_query("MATCH (:Source {id:'live/jira/SUP-1060'})-[:ASSIGNED_TO]->(p) RETURN p.name").result_set
    assert who == [["Nagarjun"]]


def test_slack_signature_verification():
    body = json.dumps({"type": "url_verification"}).encode()
    ts = str(int(time.time()))
    sig = "v0=" + hmac.new(b"s3cret", f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    assert verify_slack("s3cret", ts, body, sig)
    assert not verify_slack("s3cret", ts, body, "v0=bad")
    assert not verify_slack("s3cret", str(int(time.time()) - 3600), body, sig)
