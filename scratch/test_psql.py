import subprocess
import json

cmd = [
    "docker", "exec", "evolution_postgres",
    "psql", "-U", "evolution", "-d", "evolution", "-t", "-A",
    "-c", 'SELECT json_agg(t) FROM (SELECT id, key, message, "messageTimestamp", "instanceId" FROM "Message" WHERE (key->>\'fromMe\')::boolean = false ORDER BY "messageTimestamp" DESC LIMIT 10) t;'
]

res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
if res.returncode == 0:
    data = json.loads(res.stdout.strip())
    print(f"Sucesso! Encontradas {len(data)} mensagens recebidas:")
    for row in data:
        k = row.get("key", {})
        jid = k.get("remoteJidAlt") or k.get("remoteJid")
        ts = row.get("messageTimestamp")
        msg = row.get("message") or {}
        txt = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
        print(f"JID: {jid} | TS: {ts} | TXT: {txt[:60]}")
else:
    print("Erro:", res.stderr)
