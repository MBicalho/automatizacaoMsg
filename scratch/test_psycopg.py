import psycopg2

conn = psycopg2.connect("postgresql://evolution:evolution_pass_123@localhost:5432/evolution")
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM "Message";')
count = cur.fetchone()[0]
print(f"CONEXAO COM POSTGRES OK! Total de mensagens: {count}")
conn.close()
