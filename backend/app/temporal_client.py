from temporalio.client import Client

from app.config import TEMPORAL_ADDRESS, TEMPORAL_NAMESPACE

_client: Client | None = None


async def get_temporal_client() -> Client:
    global _client
    if _client is None:
        _client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    return _client
