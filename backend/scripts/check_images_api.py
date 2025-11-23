import urllib.request
url='http://127.0.0.1:8000/api/generated-images/'
try:
    req=urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as r:
        ct=r.getheader('Content-Type')
        body=r.read(1000)
        print('STATUS', r.status)
        print('CONTENT-TYPE', ct)
        print('BODY_PREVIEW')
        print(body.decode('utf-8', errors='replace'))
except Exception as e:
    print('ERROR', e)
