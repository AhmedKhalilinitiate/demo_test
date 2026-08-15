from crawler.adapters import adapter_for, AmazonSA, Noon, Jarir, Extra, Namshi, BaseAdapter, ProductQuote
from crawler.price_check import baseline, deal_status, _price_number, _drop_price_outliers, _should_alert
from crawler.product_match import evaluate_match


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


def test_exact_model_and_wide_variant_matching():
    good=evaluate_match('ASICS GEL KAYANO 32 wide','ASICS Gel-Kayano 32 Mens Running Shoes Wide Fit')
    assert good.accepted
    assert not evaluate_match('ASICS GEL KAYANO 32 wide','ASICS Gel-Kayano 31 Wide Running Shoes').accepted
    assert not evaluate_match('ASICS GEL KAYANO 32 wide','ASICS Gel-Kayano 32 Running Shoes').accepted


def test_edition_and_model_code_matching():
    assert evaluate_match('iPhone 15 Pro Max','Apple iPhone 15 Pro Max 256GB').accepted
    assert not evaluate_match('iPhone 15 Pro Max','Apple iPhone 15 Plus 256GB').accepted
    assert evaluate_match('Sony WH-1000XM5','Sony WH-1000XM5 Wireless Headphones').accepted
    assert not evaluate_match('Sony WH-1000XM5','Sony WH-1000XM4 Wireless Headphones').accepted


def test_price_parser_handles_saudi_and_arabic_formats():
    assert _price_number('SAR 1,299.00')==1299.0
    assert _price_number('١٬٢٩٩٫٥٠ ر.س')==1299.5
    assert _price_number('1.299,50 SAR')==1299.5


def test_obvious_price_outlier_is_removed():
    quotes=[
        ProductQuote('A','Product',600,'SAR',True,'https://a.example'),
        ProductQuote('B','Product',620,'SAR',True,'https://b.example'),
        ProductQuote('C','Product',640,'SAR',True,'https://c.example'),
        ProductQuote('Accessory','Product',99,'SAR',True,'https://d.example'),
    ]
    kept,removed=_drop_price_outliers(quotes)
    assert removed==1
    assert min(q.price for q in kept)==600


def test_repeat_alert_suppression_and_stronger_deal_alert():
    previous=[{'is_deal':True,'delivered_price':500}]
    assert not _should_alert(True,previous,495)
    assert _should_alert(True,previous,480)
    assert _should_alert(True,[{'is_deal':False,'delivered_price':600}],500)
    assert not _should_alert(False,previous,450)
