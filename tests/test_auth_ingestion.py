from types import SimpleNamespace as NS
import pytest
from sourcemind.auth import OAuthStateStore, AuthExpired, accept_session, ensure_session, clear_session, finish_google
from sourcemind.ingestion import build_document, split_page, validate_public_url, read_pdf


def test_oauth_state_survives_new_instance_and_consumes_once(tmp_path):
    path=tmp_path/'oauth.sqlite'
    OAuthStateStore(path).put('nonce','verifier')
    assert OAuthStateStore(path).consume('nonce') == 'verifier'
    with pytest.raises(AuthExpired):
        OAuthStateStore(path).consume('nonce')


def test_state_is_bound_to_nonce_and_expires(tmp_path):
    store=OAuthStateStore(tmp_path/'oauth.sqlite')
    store.put('a','secret',ttl=-1)
    with pytest.raises(AuthExpired):
        store.consume('b')
    with pytest.raises(AuthExpired):
        store.consume('a')


def test_oauth_callback_requires_same_browser_binding(tmp_path):
    store=OAuthStateStore(tmp_path/'oauth.sqlite')
    store.put('nonce','verifier')
    calls=[]
    client=NS(auth=NS(exchange_code_for_session=lambda params:calls.append(params) or 'success'))
    with pytest.raises(AuthExpired):
        finish_google(client,'code','nonce',store,'different-browser')
    assert not calls
    assert finish_google(client,'code','nonce',store,'nonce') == 'success'
    assert calls[0]['code_verifier'] == 'verifier'


def test_bad_identity_clears_all_private_session_state():
    state={'user':{'id':'a'},'access_token':'token','expires_at':10**12, 'uploads':['private'],'history':['private']}
    client=NS(auth=NS(get_user=lambda _: NS(user=NS(id='b'))))
    with pytest.raises(AuthExpired):
        ensure_session(state,client)
    assert state == {}


def test_rotated_refresh_token_is_saved():
    response=NS(user=NS(id='a',email='a@example.com',user_metadata={}),session=NS(access_token='new_access',refresh_token='new_refresh',expires_at=10**12))
    state={'user':{'id':'a'},'access_token':'old','refresh_token':'old_refresh','expires_at':0}
    attached=[]
    client=NS(auth=NS(refresh_session=lambda _:response,get_user=lambda _:NS(user=response.user)),postgrest=NS(auth=attached.append))
    assert ensure_session(state,client)['id']=='a'
    assert state['refresh_token']=='new_refresh'
    assert attached==['new_access']


def test_multiple_pages_preserve_one_based_number_and_later_page_fingerprint():
    first='An engineering document with enough readable text to index.'
    a=build_document('a.pdf','pdf',[(1,first),(2,'The 2025 measured voltage is 12 volts in this source.')])
    b=build_document('b.pdf','pdf',[(1,first),(2,'The 2025 measured voltage is 18 volts in this source.')])
    assert [c['page'] for c in a['chunks']]==[1,2]
    assert a['fingerprint'] != b['fingerprint']


def test_scanned_or_empty_pdf_does_not_index():
    with pytest.raises(ValueError,match='OCR'):
        build_document('a.pdf','pdf',[(1,'')])
    with pytest.raises(ValueError,match='not a PDF'):
        read_pdf(b'not-pdf','a.pdf')


def test_chunk_budget_and_length():
    chunks=split_page('A sentence describes the 2025 measurements. '*100)
    assert len(chunks)>1 and all(30<=len(c)<=1000 for c in chunks)


@pytest.mark.parametrize('url',['file:///etc/passwd','http://user:pass@example.com','http://example.com:3000'])
def test_invalid_url_blocked(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


def test_private_dns_and_redirect_destinations_blocked(monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo',lambda *_args,**_kwargs:[(2,1,6,'',('127.0.0.1',80))])
    with pytest.raises(ValueError,match='blocked'):
        validate_public_url('https://internal.example')
