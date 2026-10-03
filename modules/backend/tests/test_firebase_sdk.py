"""Official SDK boundary, without ADC, real ID tokens or network calls."""
import pytest
from fastapi import HTTPException
from src.config import settings
from src.services import firebase_identity

# The API image installs this SDK. Legacy ML-only test images need not do so.
firebase_admin = pytest.importorskip('firebase_admin')
from firebase_admin import auth
from google.auth.exceptions import RefreshError


def test_official_verification_requires_revocation_and_zero_clock_skew(monkeypatch):
    app = object()
    monkeypatch.setattr(settings, 'FIREBASE_PROJECT_ID', 'synthetic-project-123')
    monkeypatch.setattr(firebase_admin, 'get_app', lambda name: app)
    seen = {}
    def verify(token, **options):
        seen.update(options)
        assert token == 'synthetic-id-proof'
        return {'uid': 'synthetic-uid'}
    monkeypatch.setattr(auth, 'verify_id_token', verify)
    assert firebase_identity._verify_with_sdk('synthetic-id-proof') == {'uid': 'synthetic-uid'}
    assert seen == {'app': app, 'check_revoked': True, 'clock_skew_seconds': 0}


@pytest.mark.parametrize('failure,status', [
    (auth.InvalidIdTokenError('synthetic invalid token'), 401),
    (auth.ExpiredIdTokenError('synthetic expired token', None), 401),
    (auth.RevokedIdTokenError('synthetic revoked token'), 401),
    (auth.CertificateFetchError('synthetic certificate outage', None), 503),
    (RefreshError('synthetic ADC refresh outage'), 503),
])
def test_sdk_failures_are_safe_and_do_not_disclose_tokens(monkeypatch, failure, status):
    monkeypatch.setattr(settings, 'FIREBASE_PROJECT_ID', 'synthetic-project-123')
    monkeypatch.setattr(firebase_admin, 'get_app', lambda name: object())
    def reject(*args, **kwargs):
        raise failure
    monkeypatch.setattr(auth, 'verify_id_token', reject)
    with pytest.raises(HTTPException) as error:
        firebase_identity._verify_with_sdk('synthetic-private-proof')
    assert error.value.status_code == status
    assert 'synthetic' not in error.value.detail
