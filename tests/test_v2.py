from crawler.adapters import adapter_for, AmazonSA, Noon, Jarir, Extra, Namshi, BaseAdapter
from crawler.price_check import baseline, deal_status

def test_adapter_routing():
    assert isinstance(adapter_for('https://www.amazon.sa/dp/x'), AmazonSA)
    assert isinstance(adapter_for('https://www.noon.com/saudi-en/x'), Noon)
    assert isinstance(adapter_for('https://www.jarir.com/x'), Jarir)
    assert isinstance(adapter_for('https://www.extra.com/en-sa/x'), Extra)
    assert isinstance(adapter_for('https://www.namshi.com/saudi-en/x'), Namshi)
    assert type(adapter_for('https://shop.example/x')) is BaseAdapter

def test_jsonld_parse():
    html='<html><h1>Test Shoe</h1><script type="application/ld+json">{"@type":"Product","name":"Test Shoe","offers":{"price":"479.00","priceCurrency":"SAR","availability":"https://schema.org/InStock"}}</script></html>'
    q=BaseAdapter().parse('https://shop.example/x',html)
    assert q.price==479.0 and q.currency=='SAR' and q.in_stock

def test_deal_math():
    assert baseline([600,650,700])==650
    assert deal_status(500,650,15)[0]
    assert not deal_status(600,650,15)[0]
    assert deal_status(520,650,15,530)[0]
