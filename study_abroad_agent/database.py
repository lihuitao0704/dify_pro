import pymysql
from pymysql.cursors import DictCursor
from config import Config


class Database:

    def __init__(self):

        self.conn = pymysql.connect(

            host=Config.MYSQL_HOST,

            port=Config.MYSQL_PORT,

            user=Config.MYSQL_USER,

            password=Config.MYSQL_PASSWORD,

            database=Config.MYSQL_DATABASE,

            charset="utf8mb4",

            cursorclass=DictCursor,

            autocommit=True

        )

    def query(self, sql, params=None):

        with self.conn.cursor() as cursor:

            cursor.execute(sql, params)

            return cursor.fetchall()

    def query_one(self, sql, params=None):

        with self.conn.cursor() as cursor:

            cursor.execute(sql, params)

            return cursor.fetchone()

    def execute(self, sql, params=None):

        with self.conn.cursor() as cursor:

            cursor.execute(sql, params)

            return cursor.lastrowid

    def close(self):

        self.conn.close()


db=Database()