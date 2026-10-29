import httpx
import pytest

from automation_platform.core.http import HttpClient, HttpPolicy


def test_access_denied_is_not_retried():
    def handler(request):
        return httpx.Response(403, request=request)

    with HttpClient(HttpPolicy(retries=3), transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(httpx.HTTPStatusError):
            http.get_text('https://example.test/blocked')
        assert http.requests_count == 1


def test_transient_server_failure_is_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200, text='catalogue', request=request)

    with HttpClient(HttpPolicy(backoff_seconds=0), transport=httpx.MockTransport(handler)) as http:
        assert http.get_text('https://example.test/catalogue') == 'catalogue'
        assert http.requests_count == 2
