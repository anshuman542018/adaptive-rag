from streamlit.testing.v1 import AppTest
from sourcemind.engine import answer
from sourcemind.lab import demo_corpus, demo_cases, fixture_model


def test_login_and_lab_work_without_credentials(monkeypatch):
    monkeypatch.setattr('dotenv.load_dotenv', lambda: None)
    for key in ['SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY','SUPABASE_ANON_KEY','GROQ_API_KEY']:
        monkeypatch.delenv(key,raising=False)
    app=AppTest.from_file('app.py').run(timeout=20)
    assert not app.exception
    assert any(t.label=='Create account' for t in app.tabs)
    app.button(key='run_lab').click().run()
    assert not app.exception
    assert app.session_state['lab_report']['claims']


def test_authenticated_workspace_renders_saved_evidence(monkeypatch):
    case=demo_cases()['A claim with two supporting documents']
    report=answer(case['question'],demo_corpus(),fixture_model(case))
    class FakeRepository:
        def __init__(self,*_): pass
        def documents(self):
            return [{'id':'d1','name':'private.pdf','chunks':2,'indexed_chunks':2,'page_count':2,'added_at':'2026-10-09','summary':'Synthetic test.'}]
        def conversations(self): return [{'id':'conversation','title':'Evidence check'}]
        def rows(self,*_): return []
        def messages(self,*_):
            return [{'id':'m1','role':'user','content':case['question']},
                    {'id':'m2','role':'assistant','content':report['answer'],'evidence_report':report}]
    monkeypatch.setattr('sourcemind.repository.Repository',FakeRepository)
    monkeypatch.setattr('sourcemind.auth.ensure_session',lambda state,_:state['user'])
    app=AppTest.from_file('app.py')
    app.session_state['user']={'id':'test','name':'Test','email':'test@example.invalid'}
    app.session_state['supabase_client']=object()
    app.session_state['conversation_id']='conversation'
    app.run(timeout=20)
    assert not app.exception
    assert any(t.label=='PDF disagreements' for t in app.tabs)
    assert any(t.label=='Knowledge gaps' for t in app.tabs)


def test_google_callback_keeps_session_without_reexchanging_code(monkeypatch):
    from types import SimpleNamespace as NS
    response=NS(user=NS(id='test',email='test@example.invalid',user_metadata={}),
                session=NS(access_token='token',refresh_token='refresh',expires_at=10**12))
    exchanges=[]
    monkeypatch.setattr('sourcemind.auth.finish_google',lambda *_:exchanges.append('exchange') or response)
    monkeypatch.setattr('sourcemind.auth.ensure_session',lambda state,_:state['user'])
    monkeypatch.setattr('sourcemind.browser_binding.browser_binding',lambda *_args,**_kwargs:{'nonce':'browser-nonce'})
    class EmptyRepository:
        def __init__(self,*_): pass
        def documents(self): return []
        def conversations(self): return []
        def rows(self,*_): return []
    monkeypatch.setattr('sourcemind.repository.Repository',EmptyRepository)
    app=AppTest.from_file('app.py')
    app.session_state['supabase_client']=object()
    app.query_params['code']='single-use-code'
    app.query_params['oauth_state']='browser-nonce'
    app.run(timeout=20)
    assert not app.exception
    assert app.session_state['user']['id']=='test'
    assert any(t.label=='Source library' for t in app.tabs)
    assert app.query_params['code']=='single-use-code'  # No remount-triggering query mutation.
    app.run(timeout=20)
    assert exchanges==['exchange']
    assert not app.exception
