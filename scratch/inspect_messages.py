import urllib.request
import json
import re

for inst in ['conta_1', 'conta_2']:
    url = f'http://localhost:8080/chat/findMessages/{inst}'
    req = urllib.request.Request(url, data=json.dumps({}).encode(), headers={'apikey': 'minha_chave_secreta_123', 'Content-Type': 'application/json'})
    res = json.loads(urllib.request.urlopen(req).read().decode())
    records = res.get('messages', {}).get('records', [])
    print(f"\n=================== INSTANCE: {inst} (total {len(records)}) ===================")
    for m in records:
        k = m.get('key', {})
        jid = k.get('remoteJid', '')
        alt = k.get('remoteJidAlt', '')
        from_me = k.get('fromMe')
        ts = m.get('messageTimestamp')
        msg = m.get('message') or {}
        text = msg.get('conversation') or msg.get('extendedTextMessage', {}).get('text') or ''
        
        # Check if 5531986682759 or 553196183809 or 553399861996 or 5533998228225 is in jid or alt
        for num in ['5531986682759', '553196183809', '553399861996', '5533998228225']:
            if num in jid or num in alt:
                print(f"[{inst}] num={num} | fromMe={from_me} | ts={ts} | jid={jid} | alt={alt} | text={text[:70]}")
