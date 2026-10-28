import csv, io, json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
results=[]

def check(name, condition):
    if not condition: raise AssertionError(name)
    results.append({'case':name,'result':'PASS'})

with tempfile.TemporaryDirectory(prefix='taskflow-test-',dir=Path(__file__).parent) as temp:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env={**os.environ,'DATABASE_PATH':str(Path(temp)/'tasks.db'),'DEMO_PASSWORD':'test-password-2026','APP_ENV':'local'}
    logfile=open(Path(__file__).parent/'test-server.log','w',encoding='utf8')
    proc=None; cookie=''
    def request(path,method='GET',body=None,auth=True,header=True,raw=False):
        headers={}
        if header: headers['X-TaskFlow-Request']='1'
        if auth and cookie: headers['Cookie']=cookie
        if body is not None: headers['Content-Type']='application/json'
        data=json.dumps(body).encode() if body is not None else None
        req=Request(base+path,data=data,method=method,headers=headers)
        try: response=urlopen(req,timeout=5)
        except HTTPError as exc: response=exc
        content=response.read()
        return response.status,content if raw else json.loads(content),response.headers
    def start():
        global proc
        proc=subprocess.Popen([sys.executable,str(ROOT/'app.py'),'--port',str(port)],env=env,stdout=logfile,stderr=logfile)
        for _ in range(50):
            try:
                if request('/health')[0]==200:return
            except Exception:time.sleep(.1)
        raise RuntimeError('Server did not start')
    def stop():
        global proc
        proc.terminate(); proc.wait(timeout=10); proc=None
    def login():
        global cookie
        status,body,headers=request('/api/login','POST',{'password':'test-password-2026'},False)
        assert status==200
        cookie=headers['Set-Cookie'].split(';')[0]
    try:
        start()
        check('Health endpoint and local mode',request('/health')[1]['mode']=='local')
        check('Unauthenticated task access rejected',request('/api/tasks',auth=False)[0]==401)
        check('Missing mutation header rejected',request('/api/login','POST',{'password':'x'},False,False)[0]==403)
        check('Wrong password rejected',request('/api/login','POST',{'password':'wrong'},False)[0]==401)
        login();check('Session login accepted',request('/api/session')[1]['authenticated'])
        initial=request('/api/tasks')[1]
        check('Six sample records and correct summary',len(initial['tasks'])==6 and initial['summary']=={'todo':2,'doing':2,'done':2})
        payload={'title':'  Kiem thu EC2  ','owner':'Tester','priority':'high','status':'todo','due':'2026-11-02'}
        code,created,_=request('/api/tasks','POST',payload); task_id=created['id']
        check('Create task and trim spaces',code==201 and request('/api/tasks')[1]['tasks'][0]['title']=='Kiem thu EC2')
        check('Reject blank title',request('/api/tasks','POST',{**payload,'title':'   '})[0]==400)
        check('Reject invalid calendar date',request('/api/tasks','POST',{**payload,'due':'2026-02-30'})[0]==400)
        check('Reject unsupported status',request('/api/tasks','POST',{**payload,'status':'invalid'})[0]==400)
        check('Reject nonobject JSON',request('/api/tasks','POST',['invalid'])[0]==400)
        check('Filter by status and priority',len(request('/api/tasks?status=todo&priority=high')[1]['tasks'])==1)
        check('Search and global summary',len(request('/api/tasks?q=Kiem')[1]['tasks'])==1 and sum(request('/api/tasks?q=Kiem')[1]['summary'].values())==7)
        check('SQL injection string treated as data',len(request('/api/tasks?q=%27%20OR%201%3D1--')[1]['tasks'])==0)
        check('Update task status',request('/api/tasks/'+str(task_id),'PATCH',{'status':'done'})[0]==200 and request('/api/tasks?q=Kiem')[1]['tasks'][0]['status']=='done')
        check('Reject unknown update field',request('/api/tasks/'+str(task_id),'PATCH',{'id':100})[0]==400)
        check('Missing task returns 404',request('/api/tasks/999999','DELETE')[0]==404)
        formula={**payload,'title':'=1+1','owner':'@test'}
        formula_id=request('/api/tasks','POST',formula)[1]['id']
        code,data,_=request('/api/export',raw=True)
        rows=list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
        check('CSV UTF8 and formula neutralization',code==200 and any(row[1]=="'=1+1" and row[2]=="'@test" for row in rows[1:]))
        check('Static page and CSP',request('/',raw=True)[0]==200 and "default-src 'self'" in request('/',raw=True)[2]['Content-Security-Policy'])
        check('Path traversal denied',request('/../app.py',raw=True)[0]==404)
        stop();start()
        check('Restart invalidates old session',not request('/api/session')[1]['authenticated'])
        login()
        check('Tasks persist across process restart',len(request('/api/tasks')[1]['tasks'])==8 and request('/api/tasks?q=Kiem')[1]['tasks'][0]['status']=='done')
        check('Delete task',request('/api/tasks/'+str(formula_id),'DELETE')[0]==200 and len(request('/api/tasks')[1]['tasks'])==7)
        for task in request('/api/tasks')[1]['tasks']:request('/api/tasks/'+str(task['id']),'DELETE')
        stop();start();login()
        check('Empty database stays empty after restart',len(request('/api/tasks')[1]['tasks'])==0)
        request('/api/logout','POST',{})
        check('Logout invalidates session',request('/api/tasks')[0]==401)
    finally:
        if proc:stop()
        logfile.close()
Path(__file__).with_name('test-results.json').write_text(json.dumps({'passed':len(results),'cases':results},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'passed':len(results),'failed':0}))
