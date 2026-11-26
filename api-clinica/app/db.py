import pymysql
from flask import current_app


def get_conn(autocommit=True):
    """Abre uma conexão com o MariaDB. Uso normal (cada comando já é gravado):

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT ... WHERE id = %s", (valor,))

    Quando uma operação precisa gravar em MAIS DE UMA TABELA e as duas
    devem acontecer juntas (ou nenhuma), use autocommit=False e confirme
    manualmente (veja app/routes/tutores.py para um exemplo):

        conn = get_conn(autocommit=False)
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO ...")
                cur.execute("INSERT INTO ...")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    Sempre passe os valores em tupla com %s (nunca concatene texto no SQL,
    isso evita um ataque chamado SQL injection).
    """
    c = current_app.config
    return pymysql.connect(
        host=c["DB_HOST"],
        port=c["DB_PORT"],
        user=c["DB_USER"],
        password=c["DB_PASSWORD"],
        database=c["DB_NAME"],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=autocommit,
    )
