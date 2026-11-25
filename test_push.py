import os, requests, json
token = os.environ.get('PUSHPLUS_TOKEN')
print("token长度:", len(token) if token else 0)
r = requests.post("https://www.pushplus.plus/send",
    headers={'Content-Type':'application/json'},
    data=json.dumps({"token":token,"title":"推送测试","content":"<h3>看到这条就通了</h3>","template":"html"}).encode('utf-8'),
    timeout=15)
print("状态码:", r.status_code)
print("返回内容:", r.text)
