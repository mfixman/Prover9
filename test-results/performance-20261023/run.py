import pathlib, re, random, subprocess, concurrent.futures, json, time, os, statistics, platform, collections
ROOT=pathlib.Path(__file__).resolve().parents[2]
TPTP=ROOT.parent/'TPTP'; OUT=pathlib.Path(__file__).resolve().parent
START=time.monotonic(); SEED=2026102302; N=120
CPUS=sorted(os.sched_getaffinity(0))[:16]
os.sched_setaffinity(0,CPUS)
cache={}
def supported(p):
    if p in cache:return cache[p]
    cache[p]=False
    s=re.sub(r'%[^\n]*','',p.read_text(errors='replace'))
    if re.search(r'\b(?:fof|tff|thf|tcf)\s*\(',s) or re.search(r'\$(?!true\b|false\b)',s) or '"' in s:return False
    if re.search(r'(?<![\w])\d+(?:\.\d+)?(?![\w])',s):return False
    for m in re.finditer(r"include\s*\(\s*'([^']+)'\s*([^)]*)\)",s):
        if m[2].strip() or not supported(TPTP/m[1]):return False
    cache[p]=True;return True
pool=[]
for p in sorted((TPTP/'Problems').glob('*/*-*.p')):
    header=p.open().read(16000)
    if not re.search(r'%\s*Status\s*:\s*Unsatisfiable\b',header):continue
    if not re.search(r'%\s*SPC\s*:\s*CNF_',header):continue
    pool.append(p)
rng=random.Random(SEED); rng.shuffle(pool)
selected=[]
for p in pool:
    if supported(p):selected.append(p)
    if len(selected)==N:break
meta={'seed':SEED,'sample_size':len(selected),'candidate_pool_size_before_syntax_filter':len(pool),'scope':'Uniform shuffled CNF Unsatisfiable candidates, rejecting unsupported syntax; no size or difficulty filter. Excludes selective includes, interpreted symbols, numeric/distinct objects and FOF.','workers':16,'cpu_affinity':CPUS,'cpu_limit_seconds':20,'wall_limit_seconds':25,'memory_limit_MB':256,'conversion_wall_limit_seconds':5,'platform':platform.platform(),'cpu_model':next((x.split(':',1)[1].strip() for x in pathlib.Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name')),'unknown'),'sample':[str(p.relative_to(TPTP)) for p in selected]}
(OUT/'sample.json').write_text(json.dumps(meta,indent=2))
print('Sample ready:',len(selected),'from',len(pool),'candidates; elapsed',round(time.monotonic()-START,2),flush=True)
def run(p):
    all_start=time.monotonic(); header=p.open().read(16000)
    rating=re.search(r'%\s*Rating\s*:\s*([\d.]+)',header)
    r={'problem':p.stem,'domain':p.parent.name,'rating':float(rating[1]) if rating else None}
    try:
        t=time.monotonic()
        with p.open('rb') as f:c=subprocess.run([str(ROOT/'provers.src/tptp_to_ladr')],stdin=f,capture_output=True,cwd=TPTP,timeout=5)
        r['conversion_wall_seconds']=time.monotonic()-t
        if c.returncode:
            (OUT/(p.stem+'.conversion.log')).write_bytes(c.stdout+c.stderr)
            r['outcome']='conversion_error';return r
        inp=b'assign(max_seconds,20).\nassign(max_megs,256).\nclear(print_given).\nclear(print_initial_clauses).\nclear(print_kept).\n'+c.stdout
        (OUT/(p.stem+'.in')).write_bytes(inp)
        t=time.monotonic()
        try:
            proc=subprocess.run([str(ROOT/'provers.src/prover9')],input=inp,capture_output=True,timeout=25)
            log=proc.stdout+proc.stderr;r['exit_code']=proc.returncode
        except subprocess.TimeoutExpired as e:
            log=(e.stdout or b'')+(e.stderr or b'');r['exit_code']='wall_timeout'
        r['search_wall_seconds']=time.monotonic()-t
        (OUT/(p.stem+'.log')).write_bytes(log)
        s=log.decode(errors='replace')
        r['outcome']='proved' if 'THEOREM PROVED' in s else 'unsolved'
        why=re.search(r'Process .* exit \(([^)]+)\)',s)
        r['reason']=why[1] if why else str(r['exit_code'])
        cpu=re.findall(r'User_CPU=([\d.]+), System_CPU=([\d.]+)',s)
        if cpu:r['reported_cpu_seconds']=sum(map(float,cpu[-1]))
    except subprocess.TimeoutExpired:
        r['outcome']='conversion_timeout'
    except Exception as e:
        r['outcome']='runner_error';r['error']=repr(e)
    finally:
        r['total_wall_seconds']=time.monotonic()-all_start
        (OUT/(p.stem+'.json')).write_text(json.dumps(r,indent=2))
    return r
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
    for future in concurrent.futures.as_completed([executor.submit(run,p) for p in selected]):
        results.append(future.result())
        if len(results)%20==0:print('Completed',len(results),'proved',sum(r['outcome']=='proved' for r in results),'elapsed',round(time.monotonic()-START,1),flush=True)
solved=[r for r in results if r['outcome']=='proved']
summary={'elapsed_seconds':time.monotonic()-START,'outcomes':dict(collections.Counter(r['outcome'] for r in results)),'reasons':dict(collections.Counter(r.get('reason',r['outcome']) for r in results)),'solved_by_search_wall_seconds':{str(t):sum(r['search_wall_seconds']<=t for r in solved) for t in [.1,1,5,10,20,25]},'median_solved_search_wall_seconds':statistics.median(r['search_wall_seconds'] for r in solved) if solved else None,'median_solved_cpu_seconds':statistics.median(r['reported_cpu_seconds'] for r in solved if 'reported_cpu_seconds'in r) if solved else None,'rating_groups':[]}
for name,lo,hi in [('0.00',0,0),('(0,0.5]',0,.5),('(0.5,1]',.5,1)]:
    group=[r for r in results if r['rating'] is not None and (r['rating']==0 if hi==0 else lo<r['rating']<=hi)]
    summary['rating_groups'].append({'rating':name,'total':len(group),'proved':sum(r['outcome']=='proved' for r in group)})
(OUT/'results.json').write_text(json.dumps({'metadata':meta,'summary':summary,'results':sorted(results,key=lambda r:r['problem'])},indent=2))
print(json.dumps(summary,indent=2),flush=True)
