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
    app.session_state['omission_m2']={**report,'experiment':{'excluded_document_id':'d3','remaining_passages':2}}
    app.run(timeout=20)
    assert not app.exception
    assert not app.tabs  # The workspace opens directly to the conversation.
    assert not app.get('metric')
    assert any(e.label=='View sources & details' and not e.proto.expanded for e in app.expander)
    app.selectbox(key='detail_view_m2').select('Source dependency').run()
    assert not app.exception
    assert any(b.label=='Export alternative report' for b in app.get('download_button'))
    next(b for b in app.button if b.label=='Sources').click().run()
    assert not app.exception
    assert app.session_state['workspace_page']=='Source library'
    assert not app.chat_input
    next(b for b in app.button if b.label=='Knowledge gaps').click().run()
    assert not app.exception
    assert any(f.label=='Probe questions (one per line)' for f in app.text_area)
    app.button(key='conv_conversation').click().run()
    assert len(app.chat_message)==2
    next(b for b in app.button if b.label=='New chat').click().run()
    assert not app.exception
    assert not app.chat_message
    assert 'conversation_id' not in app.session_state


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
    assert any(b.label=='Sources' for b in app.button)
    assert app.query_params['code']==['single-use-code']  # No remount-triggering query mutation.
    app.run(timeout=20)
    assert exchanges==['exchange']
    assert not app.exception
