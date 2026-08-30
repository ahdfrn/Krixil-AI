from sqlalchemy import select

from app.models.usage_record import UsageRecord
from tests.helpers import auth_headers, register


async def test_chat_records_usage_scoped_to_tenant(client, session_factory):
    registered = await register(client)
    tenant_id = registered["tenant"]["id"]
    headers = auth_headers(registered["access_token"])

    resp = await client.post("/api/v1/chat", json={"message": "hello"}, headers=headers)
    assert resp.status_code == 200

    async with session_factory() as session:
        records = (await session.execute(select(UsageRecord))).scalars().all()

    assert len(records) == 1
    assert str(records[0].tenant_id) == tenant_id
    assert records[0].model == "mock"
    assert records[0].prompt_tokens > 0
