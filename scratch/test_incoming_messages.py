import psycopg2

conn = psycopg2.connect("postgresql://evolution:evolution_pass_123@localhost:5432/evolution")
cur = conn.cursor()

leads = [
    ("Matheus Bicalho", "5531986682759"),
    ("Maria Fernanda", "553196183809"),
    ("Daniela", "553399861996"),
    ("Eva", "5533998228225"),
]

for name, phone in leads:
    # Use last 8 digits for matching
    suffix = phone[-8:]
    pattern = f"%{suffix}%"
    
    cur.execute('''
        SELECT 
            id,
            (key->>'fromMe')::boolean as from_me,
            COALESCE(key->>'remoteJidAlt', key->>'remoteJid') as jid,
            "messageTimestamp" as ts,
            to_timestamp("messageTimestamp") as dt,
            COALESCE(
                message->>'conversation',
                message->'extendedTextMessage'->>'text',
                "messageType"
            ) as text
        FROM "Message"
        WHERE (key->>'remoteJidAlt' LIKE %s OR key->>'remoteJid' LIKE %s)
          AND (key->>'remoteJid') NOT LIKE '%%@g.us'
        ORDER BY "messageTimestamp" ASC;
    ''', (pattern, pattern))
    
    rows = cur.fetchall()
    
    # 1. Encontra o timestamp da ultima mensagem que enviamos (fromMe = True)
    last_sent_ts = 0
    for r in rows:
        if r[1] is True:  # from_me
            if r[3] > last_sent_ts:
                last_sent_ts = r[3]
                
    # 2. Pega todas as mensagens recebidas do lead APOS nossa ultima mensagem enviada
    received_after_last_sent = []
    for r in rows:
        if r[1] is False and r[3] > last_sent_ts:
            txt = (r[5] or "").strip()
            if txt:
                received_after_last_sent.append((r[3], r[4], txt))
                
    print(f"\n--- {name} ({phone}) ---")
    print(f"Total msgs no chat: {len(rows)} | Ultimo envio nosso: ts={last_sent_ts}")
    if received_after_last_sent:
        print(f"Novas respostas recebidas do lead ({len(received_after_last_sent)} msgs):")
        for ts, dt, txt in received_after_last_sent:
            print(f"  [{dt}] {txt}")
        # Como ficaria na planilha:
        resumo = " | ".join([txt for _, _, txt in received_after_last_sent])
        print(f"Texto para 'Ultima Mensagem Recebida':\n  --> {resumo}")
    else:
        print("Nenhuma resposta recebida apos nosso ultimo envio.")

conn.close()
