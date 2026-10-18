import subprocess
import json

phone = "553196183809"
sql = f"""
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
WHERE (key->>'remoteJidAlt' LIKE '%{phone}%' OR key->>'remoteJid' LIKE '%{phone}%')
ORDER BY "messageTimestamp" ASC
"""

cmd = ["docker", "exec", "evolution_postgres", "psql", "-U", "evolution", "-d", "evolution", "-t", "-A", "-c", f"SELECT json_agg(t) FROM ({sql}) t;"]
res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
print("returncode:", res.returncode)
print("stderr:", res.stderr)
print("stdout length:", len(res.stdout))
if res.returncode == 0 and res.stdout.strip():
    msgs = json.loads(res.stdout.strip())
    print(f"Total mensagens com {phone}: {len(msgs)}")
    for m in msgs[-15:]:
        direction = ">>> ENVIADA" if m["from_me"] else "<<< RECEBIDA"
        print(f"[{m['dt']}] {direction}: {m['text'][:70]}")
