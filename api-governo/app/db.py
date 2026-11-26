import pymysql
from flask import current_app


def get_conn():
    c = current_app.config
    return pymysql.connect(
        host=c["DB_HOST"],
        port=c["DB_PORT"],
        user=c["DB_USER"],
        password=c["DB_PASSWORD"],
        database=c["DB_NAME"],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
