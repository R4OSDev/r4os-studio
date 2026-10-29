import json,os,sqlite3,unittest,uuid
from authorization import authorize,authorize_job,PERMISSIONS
from contracts import DevelopmentFault
from lease import birth
import test_jobs

class AuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.fixture=test_jobs.JobsTest();self.fixture.setUp();self.store=self.fixture.store
        self.run,self.session=str(uuid.uuid4()),str(uuid.uuid4());self.owner={'sessionId':self.session,'agentRunId':self.run}
        directory=self.store.projects/self.store.id/'Sessions';directory.mkdir();self.db=sqlite3.connect(directory/'Sessions.sqlite')
        self.db.execute('CREATE TABLE sessions(id TEXT,revision INTEGER)');self.db.execute('CREATE TABLE runs(id TEXT,session_id TEXT,busy INTEGER,state TEXT,worker TEXT,config TEXT)');self.db.execute('INSERT INTO sessions VALUES(?,1)',(self.session,))
        self.config={'revision':1,'projectPins':self.store.project['pins'],'engine':{'profile':'studio-tools-v2'},'permissions':{'studio.'+name:True for name in PERMISSIONS.values()}}
        self.db.execute('INSERT INTO runs VALUES(?,?,1,?,?,?)',(self.run,self.session,'running',json.dumps({'pid':os.getpid(),'birth':birth(os.getpid())}),json.dumps(self.config)));self.db.commit()
        self.job,_=self.store.admit('build',self.fixture.input(),self.owner)
    def tearDown(self):self.db.close();self.fixture.tearDown()
    def save(self):self.db.execute('UPDATE runs SET config=?',(json.dumps(self.config),));self.db.commit()
    def test_each_call_denied_when_disabled_and_foreign_session_never_admitted(self):
        for op,name in PERMISSIONS.items():
            self.config['permissions']['studio.'+name]=False;self.save()
            with self.assertRaises(DevelopmentFault):authorize(self.store,self.owner,op,os.getpid(),self.job)
            self.config['permissions']['studio.'+name]=True;self.save()
        with self.assertRaises(DevelopmentFault):authorize(self.store,self.owner,'input',os.getpid(),{**self.job,'sessionId':str(uuid.uuid4())})
        with self.assertRaises(DevelopmentFault):authorize(self.store,self.owner,'save_settings',os.getpid())
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],1)
    def test_pid_birth_revision_profile_and_stopping_gate(self):
        authorize(self.store,self.owner,'build',os.getpid(),self.job)
        for profile in ('studio-tools-v8', 'studio-tools-v9','studio-tools-v10','studio-tools-v14'):
            self.config['engine']['profile']=profile;self.save()
            authorize(self.store,self.owner,'build',os.getpid(),self.job)
            authorize(self.store,self.owner,'vm_start',os.getpid(),self.job)
            authorize_job(self.store,self.job)
        self.db.execute('UPDATE runs SET worker=?',(json.dumps({'pid':os.getpid(),'birth':'wrong'}),));self.db.commit()
        with self.assertRaises(DevelopmentFault):authorize(self.store,self.owner,'build',os.getpid(),self.job)
        self.db.execute('UPDATE runs SET worker=?,state=?',(json.dumps({'pid':os.getpid(),'birth':birth(os.getpid())}),'stopping'));self.db.commit()
        with self.assertRaises(DevelopmentFault):authorize(self.store,self.owner,'input',os.getpid(),self.job)
        authorize(self.store,self.owner,'cancel_owned',os.getpid(),stopping=True)
        with self.assertRaises(DevelopmentFault):authorize_job(self.store,self.job)
        authorize_job(self.store,self.job,allow_stopping=True)
        self.db.execute('UPDATE runs SET state=?,busy=0',('completed',));self.db.commit();authorize_job(self.store,self.job)
        with self.assertRaises(DevelopmentFault):authorize(self.store,self.owner,'capture',os.getpid(),self.job)
