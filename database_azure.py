import pyodbc
import streamlit as st


DB_CONFIG = {
    'server': 'servidor-midnight-04.database.windows.net', # O nome do seu servidor no Canadá
    'database': 'financasdb',
    'username':
    'password': 
    'driver': '{ODBC Driver 17 for SQL Server}' # Driver padrão do Windows
}

def get_connection():
    conn_str = (
        f"DRIVER={DB_CONFIG['driver']};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['username']};"
        f"PWD={DB_CONFIG['password']}"
    )
    return pyodbc.connect(conn_str)

def inicializar_banco_azure():
    conn = get_connection()
    cursor = conn.cursor()
    

    cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='users' AND xtype='U')
        CREATE TABLE users (
            id INT PRIMARY KEY IDENTITY(1,1),
            username NVARCHAR(100) UNIQUE,
            password NVARCHAR(MAX)
        )
    ''')
    
    cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='transacoes' AND xtype='U')
        CREATE TABLE transacoes (
            id INT PRIMARY KEY IDENTITY(1,1),
            valor FLOAT,
            loja NVARCHAR(255),
            data_compra DATE,
            banco_origem NVARCHAR(100),
            tipo NVARCHAR(50),
            user_id INT
        )
    ''')
    

    
    conn.commit()
    conn.close()
