import requests

url = "http://localhost:8080/chat/findMessages/conta_2"
headers = {"apikey": "minha_chave_secreta_123", "Content-Type": "application/json"}

# Test 1: remoteJid
payload1 = {"where": {"key": {"remoteJid": "5531986682759@s.whatsapp.net"}}}
r1 = requests.post(url, headers=headers, json=payload1).json()
print("Test 1 (remoteJid exact):", len(r1.get("messages", {}).get("records", [])))

# Test 2: remoteJid contains
payload2 = {"where": {"key": {"remoteJid": {"contains": "5531986682759"}}}}
r2 = requests.post(url, headers=headers, json=payload2).json()
print("Test 2 (remoteJid contains):", len(r2.get("messages", {}).get("records", [])))

# Test 3: without where but with limit
payload3 = {"limit": 100}
r3 = requests.post(url, headers=headers, json=payload3).json()
print("Test 3 (limit 100):", len(r3.get("messages", {}).get("records", [])))
