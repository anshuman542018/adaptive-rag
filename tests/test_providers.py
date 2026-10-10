from types import SimpleNamespace as NS
import pytest
from sourcemind.providers import run_model, ModelServiceError


class Failure(Exception):
    def __init__(self,status,code=None):
        self.status_code=status
        self.code=code
        super().__init__('private-key-and-document-contents')


def fake_factory(outcomes,calls):
    def create(**kwargs):
        calls.append(kwargs['model'])
        value=outcomes.pop(0)
        if isinstance(value,Exception): raise value
        return NS(choices=[NS(message=NS(content=value))])
    return lambda **_:NS(chat=NS(completions=NS(create=create)))


def test_unavailable_model_uses_one_bounded_fallback(caplog):
    calls=[]
    result=run_model('private-key','old-model','Return JSON',{},client_factory=fake_factory([Failure(404,'model_not_found'),'{"claims":[]}'],calls))
    assert result=={'claims':[]}
    assert calls==['old-model','openai/gpt-oss-20b']
    assert 'private-key' not in caplog.text


@pytest.mark.parametrize('status,category',[(401,'authentication'),(429,'rate_limit'),(500,'unavailable')])
def test_non_model_errors_do_not_try_a_different_model(status,category,caplog):
    calls=[]
    with pytest.raises(ModelServiceError) as error:
        run_model('private-key','model','Return JSON',{},client_factory=fake_factory([Failure(status)],calls))
    assert error.value.category==category
    assert calls==['model']
    assert 'private-key' not in str(error.value) and 'document-contents' not in caplog.text


def test_model_permissions_can_fallback_but_general_permission_denial_cannot():
    calls=[]
    assert run_model('key','model','JSON',{},client_factory=fake_factory([Failure(403,'model_permission_denied'),'{}'],calls))=={}
    with pytest.raises(ModelServiceError):
        run_model('key','model','JSON',{},client_factory=fake_factory([Failure(403)],[]))


def test_bad_json_fails_closed():
    with pytest.raises(ModelServiceError,match='unreadable'):
        run_model('key','model','JSON',{},client_factory=fake_factory(['not json'],[]))
