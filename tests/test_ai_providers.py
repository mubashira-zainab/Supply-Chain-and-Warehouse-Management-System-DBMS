"""Provider fallback test with simulated HTTP replies (no API key or internet needed)."""
import os, sys, json
os.environ.update(GEMINI_API_KEY='g-key', GROQ_API_KEY='q-key')   # fake keys, no network used
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_assistant as A, config, requests
calls=[]
class R:
    def __init__(s,code,js=None,txt=''): s.status_code=code; s._j=js; s.text=txt
    def json(s): return s._j
def gem_ok(t): return R(200,{'candidates':[{'content':{'parts':[{'text':t}]}}]})
def groq_ok(t): return R(200,{'choices':[{'message':{'content':t}}]})
def run(plan):
    it=iter(plan)
    def post(url, **kw):
        calls.append((url.split('/')[2], url.split('/')[-1].split(':')[0], kw.get('headers',{}).get('x-goog-api-key') or kw['headers'].get('Authorization')))
        r=next(it)
        if isinstance(r,Exception): raise r
        return r
    requests.post=post
# 1. first gemini model 404 -> second model works
calls.clear(); run([R(404,txt='nf'), gem_ok('hello')])
print(A.chat('sys',[{'role':'user','content':'x'}]), [c[1] for c in calls])
# 2. gemini key invalid (403) -> straight to groq (skips remaining gemini models)
calls.clear(); run([R(403,txt='bad key'), groq_ok('from groq')])
print(A.chat('sys',[{'role':'user','content':'x'}]), [c[:2] for c in calls])
# 3. everything fails -> AIUnavailable, key never leaked in message
calls.clear(); run([R(429,txt='quota')]*3+[R(500,txt='x'),R(500,txt='x')]+[requests.Timeout()]*3)
try: A.chat('sys',[{'role':'user','content':'x'}])
except A.AIUnavailable as e: print('AIUnavailable:', str(e)[:160], '| key leaked:', 'g-key' in str(e) or 'q-key' in str(e))
# 4. request shape
calls.clear()
seen={}
def post(url, **kw): seen.update(url=url, body=kw['json'], h=kw['headers']); return gem_ok('ok')
requests.post=post; A._gemini('gemini-3.8-flash','SYS',[{'role':'user','content':'q'},{'role':'assistant','content':'a'}])
print(seen['url'], list(seen['h']), [c['role'] for c in seen['body']['contents']], 'key in url:', 'key=' in seen['url'])
