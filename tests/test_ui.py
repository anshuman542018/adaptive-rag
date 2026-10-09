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
