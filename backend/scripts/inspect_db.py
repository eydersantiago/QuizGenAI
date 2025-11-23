import sqlite3
import pprint

conn = sqlite3.connect('db.sqlite3')
cur = conn.cursor()

cur.execute("PRAGMA table_info('generated_image')")
cols = cur.fetchall()
print('TABLE INFO:')
pp = pprint.PrettyPrinter(indent=2)
pp.pprint(cols)

cur.execute("PRAGMA foreign_key_list('generated_image')")
fks = cur.fetchall()
print('\nFOREIGN KEYS:')
pp.pprint(fks)

conn.close()