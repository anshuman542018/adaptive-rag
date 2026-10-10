import copy
import pytest
from sourcemind.engine import (Passage, answer, retrieve, valid_quote, source_stress,
                              contradiction_scan, fingerprint, omission_experiment)
from sourcemind.lab import demo_corpus, demo_cases, fixture_model


@pytest.mark.parametrize('case', list(demo_cases().values()))
def test_demo_grounded_claims(case):
    result = answer(case['question'], demo_corpus(), fixture_model(case))
    assert result['claims']
    sources = {s['id']: s for s in result['sources']}
    for claim in result['claims']:
        for evidence in claim['evidence']:
            assert valid_quote(evidence['quote'], sources[evidence['id']]['text'])
    if case['kind'] == 'missing':
        assert len(result['rejected_claims']) == 1
        assert '$7 million' not in result['answer']
    if case['kind'] == 'redundant':
        assert result['stress']['independently_cited_claims'] == 1
        assert all(r['retained_fraction'] == 1 for r in result['stress']['removals'])


def test_empty_corpus_does_not_call_model():
    result = answer('What is the revenue?', [], lambda *_: pytest.fail('Unexpected model call'))
    assert result['status'] == 'abstained'
    assert result['metrics']['model_calls'] == 0


def test_exact_entity_lexical_retrieval():
    corpus = [Passage('1','a','A',1,'The XR-742 device must operate below 19 volts.'),
              Passage('2','b','B',1,'General devices require a power supply and input voltage.')]
    assert retrieve('XR-742 voltage', corpus)[0].passage.id == '1'


def test_dense_paraphrase_retrieval():
    corpus = [Passage('1','a','A',1,'The workforce receives annual paid leave.', [1.,0.]),
              Passage('2','b','B',1,'Office furniture is wooden.', [0.,1.])]
    assert retrieve('employee vacation', corpus, [1.,0.])[0].passage.id == '1'


def model_with_audit(audit):
    def call(system, payload):
        if 'Audit proposed claims' in system:
            return audit
        return {'claims': [{'claim': 'Orion earned $12 million.', 'evidence': [{'id':'E1','quote':payload['passages'][0]['text']}]}]}
    return call


@pytest.mark.parametrize('audit', [
    {'checks': []}, {'checks':[{'index':0,'status':'supported','evidence_ids':['E999']}]},
    {'checks':[{'index':0,'status':'insufficient','evidence_ids':['E1']}]},
    {'checks':[{'index':0,'status':'supported','evidence_ids':['E1']}, {'index':0,'status':'supported','evidence_ids':['E1']}]},
    {'checks':'bad'}, {'checks':[{'index':False,'status':'supported','evidence_ids':['E1']}]},
])
def test_bad_audit_never_displays_claim(audit):
    result = answer('Orion revenue', demo_corpus()[:1], model_with_audit(audit))
    assert result['status'] == 'abstained'
    assert result['claims'] == []


def test_judge_failure_discards_draft():
    def call(system,payload):
        if 'Audit proposed claims' in system:
            raise TimeoutError()
        return {'claims':[{'claim':'Orion earned $12 million.', 'evidence':[{'id':'E1','quote':payload['passages'][0]['text']}]}]}
    assert answer('Orion revenue', demo_corpus()[:1],call)['claims'] == []


def test_fabricated_quote_rejected_before_audit():
    def call(system,payload):
        assert 'Audit proposed claims' not in system
        return {'claims':[{'claim':'Invented answer.', 'evidence':[{'id':'E1','quote':'Completely invented citation that does not occur.'}]}]}
    report=answer('Orion revenue',demo_corpus()[:1],call)
    assert not report['claims'] and len(report['rejected_claims']) == 1


def test_full_text_fingerprint():
    assert fingerprint('x'*500+'A') != fingerprint('x'*500+'B')


def test_near_identical_numeric_conflict_is_not_skipped():
    corpus = demo_corpus()[:2]
    corpus[0].embedding = [1.,0.]
    corpus[1].embedding = [1.,0.]
    result=contradiction_scan(corpus,fixture_model({'kind':'conflict'}))
    assert result['checked_pairs'] == 1
    assert result['findings'][0]['kind'] == 'contradiction'
    assert result['findings'][0]['page_a'] in (3,7)


def test_conflict_requires_quotes_from_both_pages():
    def call(*_):
        return {'findings':[{'pair':0,'kind':'contradiction','quote_a':'A forged citation of a totally different fact.','quote_b':'Another forged citation of a different fact.'}]}
    result=contradiction_scan(demo_corpus()[:2],call)
    assert result['findings'] == []
    assert result['failed_pairs'] == 1


@pytest.mark.parametrize('kind', ['different_scope', 'temporal_change'])
def test_noncontradiction_classifications_stay_separate(kind):
    def call(_,payload):
        pair=payload['pairs'][0]
        return {'findings':[{'pair':0,'kind':kind,'quote_a':pair['a']['text'],'quote_b':pair['b']['text']}]}
    assert contradiction_scan(demo_corpus()[:2],call)['findings'][0]['kind'] == kind


def test_source_removal_counts_document_not_chunks():
    sources={'E1':Passage('1','d1','A',1,'Evidence.'), 'E2':Passage('2','d1','A',2,'Evidence.')}
    stress=source_stress([{'evidence':[{'id':'E1'},{'id':'E2'}]}],sources)
    assert stress['removals'][0]['retained_fraction'] == 0
    assert stress['independently_cited_claims'] == 0


def test_query_planning_is_bounded():
    case=demo_cases()['Conflicting revenue figures']
    base=fixture_model(case)
    def call(system,payload):
        if 'Create at most 3' in system:
            return {'queries':['Orion revenue']*100}
        return base(system,payload)
    report=answer(case['question'],demo_corpus(),call,mode='forensic')
    assert len(report['trace'][0]['queries']) <= 3
    assert report['metrics']['model_calls'] <= 3


def test_omission_reruns_pipeline_and_cannot_cite_removed_document():
    case=demo_cases()['A claim with two supporting documents']
    report=omission_experiment(case['question'],demo_corpus(),'d3',fixture_model(case))
    assert report['claims']
    assert all(s['document_id'] != 'd3' for s in report['sources'])
    assert report['metrics']['model_calls'] == 2
    assert report['experiment']['remaining_passages'] == 3


def test_omitting_only_document_abstains_without_calling_model():
    report=omission_experiment('Orion revenue',demo_corpus()[:1],'d1',lambda *_:pytest.fail('No model call expected'))
    assert report['status'] == 'abstained'
    assert report['sources'] == []


def test_answer_disagreement_requires_two_audited_claims_and_sources():
    case=demo_cases()['Conflicting revenue figures']
    base=fixture_model(case)
    def call(system,payload):
        response=base(system,payload)
        if 'Audit proposed claims' in system:
            response['disagreements']=[{'claim_indices':[0,1],'kind':'contradiction','explanation':'The same annual revenue differs across reports.'},
                                      {'claim_indices':[0,99],'kind':'contradiction','explanation':'Invalid index'},
                                      {'claim_indices':[0,0],'kind':'contradiction','explanation':'Same claim'}]
        return response
    report=answer(case['question'],demo_corpus(),call)
    assert report['status']=='partial'
    assert len(report['disagreements'])==1
    assert len(report['disagreements'][0]['claims'])==2
    assert report['limitations']
