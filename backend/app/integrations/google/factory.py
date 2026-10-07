from functools import lru_cache

from app.core.config import get_settings
from app.integrations.google.demo import DemoGoogleApi
from app.integrations.google.http_client import HttpGoogleApi
from app.integrations.google.types import GoogleApi


@lru_cache
def get_google_api() -> GoogleApi:
    """The Google client. Used as a FastAPI dependency so tests can substitute a fake.
    Whether Google is *configured* (client id/secret) is checked by the service."""
    if get_settings().google_demo:
        return DemoGoogleApi()
    return HttpGoogleApi()
