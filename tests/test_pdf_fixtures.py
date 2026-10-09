from pathlib import Path
from sourcemind.ingestion import read_pdf


def test_physical_pdf_pages_extract_correct_values():
    docs=[]
    for name,amount in [('orion-finance-report.pdf',12),('orion-investor-brief.pdf',18)]:
        path=Path('output/pdf')/name
        document=read_pdf(path.read_bytes(),name)
        assert document['page_count']==2
        assert any(c['page']==2 and f'${amount} million' in c['content'] for c in document['chunks'])
        assert all(c['page'] in (1,2) for c in document['chunks'])
        docs.append(document)
    assert docs[0]['fingerprint'] != docs[1]['fingerprint']
