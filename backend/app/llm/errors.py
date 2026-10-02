class LLMError(Exception):
    """The model provider failed (network, auth, rate limit, bad response).

    Adapters raise this so the rest of the app never depends on a vendor SDK's
    exception types.
    """
