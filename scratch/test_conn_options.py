import pyodbc

# Test 1: exact string from functions.py with Encrypt=no
s1 = "Driver={ODBC Driver 17 for SQL Server};Server=localhost\\SQLEXPRESS;Database=AUTOMATIZACAO;Trusted_Connection=yes;Encrypt=no;TrustServerCertificate=yes;"
print("Test 1 (with Encrypt=no):", end=" ")
try:
    c = pyodbc.connect(s1, timeout=3)
    print("SUCCESS")
    c.close()
except Exception as e:
    print("FAIL:", e)

# Test 2: without Encrypt
s2 = "Driver={ODBC Driver 17 for SQL Server};Server=localhost\\SQLEXPRESS;Database=AUTOMATIZACAO;Trusted_Connection=yes;TrustServerCertificate=yes;"
print("Test 2 (without Encrypt):", end=" ")
try:
    c = pyodbc.connect(s2, timeout=3)
    print("SUCCESS")
    c.close()
except Exception as e:
    print("FAIL:", e)

# Test 3: with TCP port (127.0.0.1,1433)
s3 = "Driver={ODBC Driver 17 for SQL Server};Server=127.0.0.1\\SQLEXPRESS;Database=AUTOMATIZACAO;Trusted_Connection=yes;TrustServerCertificate=yes;"
print("Test 3 (127.0.0.1\\SQLEXPRESS):", end=" ")
try:
    c = pyodbc.connect(s3, timeout=3)
    print("SUCCESS")
    c.close()
except Exception as e:
    print("FAIL:", e)

# Test 4: SQL Auth with UID/PWD (admin / 219021@charizard)
s4 = "Driver={ODBC Driver 17 for SQL Server};Server=localhost\\SQLEXPRESS;Database=AUTOMATIZACAO;UID=admin;PWD=219021@charizard;TrustServerCertificate=yes;"
print("Test 4 (SQL Auth):", end=" ")
try:
    c = pyodbc.connect(s4, timeout=3)
    print("SUCCESS")
    c.close()
except Exception as e:
    print("FAIL:", e)
