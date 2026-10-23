import pathlib, re, random, subprocess, concurrent.futures, json, time, os
ROOT=pathlib.Path(__file__).resolve().parents[2]
TPTP=ROOT.parent/'TPTP'
OUT=pathlib.Path(__file__).resolve().parent
start=time.monotonic()
rng=random.Random(20261023)
paths=sorted((TPTP/'Problems').glob('*/*.p'))
rng.shuffle(paths)
selected=[]
def supported(p,seen=None):
    seen=set() if seen is None else seen
    if p in seen: return True
    seen.add(p)
    s=p.read_text(errors='replace')
    s=re.sub(r'%[^\n]*','',s)
    if re.search(r'\b(?:tff|thf|tcf)\s*\(',s) or re.search(r'\$(?!true\b|false\b)',s): return False
    for m in re.finditer(r"include\s*\(\s*'([^']+)'\s*([^)]*)\)",s):
        if m[2].strip(): return False # converter ignores selection lists
        child=TPTP/m[1]
        if not child.exists() or not supported(child,seen): return False
    return True
for p in paths:
    if '+' not in p.name and '-' not in p.name: continue
    s=p.read_text(errors='replace')
    m=re.search(r'%\s*Status\s*:\s*(\w+)',s)
    if not m or m[1] not in ('Theorem','Unsatisfiable','Satisfiable','CounterSatisfiable'): continue
    if not supported(p): continue
    selected.append((p,m[1]))
    if len(selected)==32: break
(OUT/'sample.json').write_text(json.dumps({'seed':20261023,'sampling':'Shuffle sorted local TPTP problem paths; first 32 supported untyped FOF/CNF with known status, no selective includes or interpreted symbols except $true/$false.','sample':[(str(p.relative_to(TPTP)),s) for p,s in selected]},indent=2))
def run(item):
    p,status=item
    t=time.monotonic()
    prior=OUT/(p.stem+'.log')
    if prior.exists():
        output=prior.read_bytes()
        proof=b'THEOREM PROVED' in output
        reason=re.search(rb'Process .* exit \(([^)]+)\)',output)
        return {'problem':p.stem,'expected':status,'result':('consistent_proof' if status in ('Theorem','Unsatisfiable') else 'CONTRADICTION') if proof else 'inconclusive','reason':reason[1].decode() if reason else 'wall_timeout_or_other','reused_saved_run':True}
    try:
        with p.open('rb') as f:
            c=subprocess.run([str(ROOT/'provers.src/tptp_to_ladr')],stdin=f,capture_output=True,cwd=TPTP,timeout=10)
    except subprocess.TimeoutExpired:
        return {'problem':p.stem,'expected':status,'result':'conversion_timeout','seconds':round(time.monotonic()-t,3)}
    (OUT/(p.stem+'.conversion.log')).write_bytes(c.stderr)
    r={'problem':p.stem,'expected':status,'conversion_exit':c.returncode}
    if c.returncode:
        r.update(result='conversion_error',seconds=round(time.monotonic()-t,3)); return r
    inp=b'assign(max_seconds, 10).\nassign(max_megs, 256).\n'+c.stdout
    (OUT/(p.stem+'.in')).write_bytes(inp)
    try:
        result=subprocess.run([str(ROOT/'provers.src/prover9')],input=inp,capture_output=True,timeout=15)
        output=result.stdout+result.stderr
        r['exit']=result.returncode
    except subprocess.TimeoutExpired as e:
        output=(e.stdout or b'')+(e.stderr or b'')
        r['exit']='wall_timeout'
    (OUT/(p.stem+'.log')).write_bytes(output)
    proof=b'THEOREM PROVED' in output
    r['result']=('consistent_proof' if status in ('Theorem','Unsatisfiable') else 'CONTRADICTION') if proof else 'inconclusive'
    r['seconds']=round(time.monotonic()-t,3)
    return r
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    results=list(pool.map(run,selected))
(OUT/'results.json').write_text(json.dumps({'elapsed_seconds':round(time.monotonic()-start,2),'workers':8,'cpu_seconds_per_problem':10,'wall_seconds_per_problem':15,'results':results},indent=2))
for r in results: print(r,flush=True)
print('Elapsed:',round(time.monotonic()-start,2),flush=True)
