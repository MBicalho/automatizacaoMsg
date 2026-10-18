import pyodbc

servers = [
    r"localhost\SQLEXPRESS",
    r"127.0.0.1\SQLEXPRESS",
    r".\SQLEXPRESS",
    r"(local)\SQLEXPRESS",
    r"localhost",
    r"127.0.0.1,1433",
    r"np:\\.\pipe\MSSQL$SQLEXPRESS\sql\query",
]

drivers = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "SQL Server",
]

installed_drivers = [d for d in pyodbc.drivers() if "SQL" in d]
print("Installed SQL drivers:", installed_drivers)

found = False
for s in servers:
    for d in installed_drivers:
        conn_str = f"Driver={{{d}}};Server={s};Database=AUTOMATIZACAO;Trusted_Connection=yes;TrustServerCertificate=yes;"
        print(f"Testing: Driver={{{d}}}, Server={s} ...", end=" ", flush=True)
        try:
            conn = pyodbc.connect(conn_str, timeout=3)
            print(">>> SUCCESS! <<<")
            conn.close()
            found = True
            break
        except Exception as e:
            err_msg = str(e).split("\n")[0]
            print(f"FAILED ({err_msg[:60]})")
    if found:
        break
