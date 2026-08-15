from __future__ import annotations
import json, os, random, statistics, smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

DATA = Path('data/price_history.json')
TRACKERS = Path('data/trackers.json')

@dataclass
class Observation:
    name: str
    country: str
    currency: str
    price: float
    url: str | None
    checked_at: str


def baseline(prices: list[float]) -> float:
    if not prices:
        return 0.0
    return float(statistics.median(prices[-30:]))


def is_deal(current: float, base: float, threshold_pct: float, target_price: float | None = None) -> bool:
    if base and current <= base * (1 - threshold_pct / 100):
        return True
    return bool(target_price and current <= target_price)


def simulated_price(name: str, target: float | None = None) -> float:
    seed = sum(ord(c) for c in name) + datetime.now(timezone.utc).timetuple().tm_yday
    random.seed(seed)
    anchor = target or 650
    return round(anchor * random.uniform(0.82, 1.18), 2)


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return default


def send_email(subject: str, body: str):
    host = os.getenv('SMTP_HOST')
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASSWORD')
    recipient = os.getenv('ALERT_EMAIL_TO')
    sender = os.getenv('ALERT_EMAIL_FROM', user)
    if not all([host, user, password, recipient, sender]):
        print('Email skipped: SMTP secrets are not configured.')
        return
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient
    msg.set_content(body)
    with smtplib.SMTP_SSL(host, int(os.getenv('SMTP_PORT', '465'))) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)


def run():
    trackers = load_json(TRACKERS, [])
    history = load_json(DATA, [])
    alerts = []
    now = datetime.now(timezone.utc).isoformat()
    by_name = {}
    for row in history:
        by_name.setdefault(row['name'], []).append(float(row['price']))
    for t in trackers:
        price = simulated_price(t['name'], t.get('targetPrice'))
        obs = Observation(t['name'], t.get('country', 'SA'), t.get('currency', 'SAR'), price, t.get('url'), now)
        base = baseline(by_name.get(t['name'], [])) or price
        row = obs.__dict__ | {'baseline': base, 'discount_pct': round(((base-price)/base)*100, 2) if base else 0}
        history.append(row)
        if is_deal(price, base, float(t.get('threshold', 15)), t.get('targetPrice')):
            alerts.append(row)
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(history[-2000:], indent=2), encoding='utf-8')
    if alerts:
        body = '\n'.join([f"{a['name']}: {a['currency']} {a['price']} vs baseline {a['baseline']} ({a['discount_pct']}%)" for a in alerts])
        send_email(f'Price alert: {len(alerts)} deal(s)', body)
    print(f'Checked {len(trackers)} trackers, alerts={len(alerts)}')

if __name__ == '__main__':
    run()
