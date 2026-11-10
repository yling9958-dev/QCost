"""Save the entire real-node pool before outcome-blind coverage sampling."""
import argparse,csv,hashlib,json
from pathlib import Path
import numpy as np
PROJECT=Path(__file__).resolve().parents[1]
CFG=json.loads((PROJECT/'configs/standalone_protocol.json').read_text())
def sha(path):
 return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def js(path,value):
 with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False)
def csvout(path,rows):
 if not rows:return
 keys=list(dict.fromkeys(k for row in rows for k in row))
 with Path(path).open('x',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(rows)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--source-root',type=Path,required=True,help='External saved 20k NPZ samples and data/traces memberships')
 p.add_argument('--output',type=Path,required=True)
 args=p.parse_args();ROOT=args.source_root.resolve();OUT=args.output
 OUT.mkdir(parents=True,exist_ok=False)
 full=[];unique={};prov=[]
 for dataset in CFG['datasets']:
  source=ROOT/'data'/f'{dataset}_20000'
  with np.load(source/'points.npz') as z:points=z['points']
  with np.load(source/'queries.npz') as z:queries=z['train']
  prov.append({'Dataset':dataset,'NodeID':'ALL','Seed':CFG['sample_seed'],'Configuration':'ALL','Method':'source','RunID':'census',
    'Points':len(points),'TrainQueries':len(queries),'CopiedInput':str(source/'points.npz'),'SHA256':sha(source/'points.npz'),
    'OriginalProvenance':str(source/'manifest.json'),'SamplingScope':'saved GeoLife reproduction sample' if dataset=='geolife' else 'saved bounded CSV-prefix sample; not full-source random sample'})
  for file in sorted((ROOT/'data/traces'/f'{dataset}_20000').glob('*/*/metadata.json')):
   m=json.loads(file.read_text());assert m['status']=='PASS'
   with np.load(file.parent/'decision_members.npz') as members:
    for d in m['decisions']:
     ix=np.sort(members[f'node_{d["node_id"]}']);local=points[ix]
     bounds=np.r_[local.min(0),local.max(0)];q=queries[(queries[:,2]>=bounds[0])&(queries[:,0]<=bounds[2])&(queries[:,3]>=bounds[1])&(queries[:,1]<=bounds[3])]
     key=hashlib.sha256(ix.astype('<i8').tobytes()).hexdigest();uid=dataset+'_'+key[:16]
     area=float(np.prod(bounds[2:]-bounds[:2]));eligible=len(ix)>=2048 and len(q)>0 and d['depth']<8
     r={'Dataset':dataset,'NodeID':d['node_id'],'NodeUID':uid,'Seed':m['seed'],'SampleSeed':CFG['sample_seed'],
      'Configuration':'UNMEASURED','Method':m['method'],'RunID':'census','NodeSize':len(ix),'Depth':d['depth'],
      'BoundingBox':json.dumps(bounds.tolist()),'Area':area,'Density':len(ix)/max(area,1e-30),'QueryCount':len(q),
      'StateSHA256':key,'MembershipKey':f'node_{d["node_id"]}','SourceFile':str(file.relative_to(ROOT)),
      'MembershipFile':str((file.parent/'decision_members.npz').relative_to(ROOT)),'CandidateEligible':eligible}
     full.append(r)
     if eligible and uid not in unique:unique[uid]=r
 csvout(OUT/'complete_candidate_node_census.csv',full)
 candidates=list(unique.values());csvout(OUT/'deduplicated_candidate_nodes.csv',candidates)
 chosen=[];rng=np.random.default_rng(CFG['sample_seed'])
 for dataset in CFG['datasets']:
  rows=sorted([r for r in candidates if r['Dataset']==dataset],key=lambda r:r['NodeUID'])
  features=np.array([[r['NodeSize'],r['Density'],r['QueryCount'],r['Depth']] for r in rows],float)
  ranks=np.empty_like(features)
  for j in range(4):
   vals=features[:,j]
   for i,v in enumerate(vals):ranks[i,j]=(np.count_nonzero(vals<v)+.5*np.count_nonzero(vals==v))/len(vals)
  priority=rng.random(len(rows));root=next(i for i,r in enumerate(rows) if r['NodeSize']==20000)
  selected=[root]
  while len(selected)<min(CFG['maximum_attempts_per_dataset'],len(rows)):
   distance=((ranks[:,None,:]-ranks[selected][None,:,:])**2).sum(2).min(1);distance[selected]=-1
   index=max(range(len(rows)),key=lambda i:(distance[i],priority[i]));selected.append(index)
  for order,i in enumerate(selected):chosen.append(dict(rows[i],AttemptOrder=order,SelectionRule='root then rank-feature maximin; no outcome input'))
 csvout(OUT/'frozen_node_attempt_order.csv',chosen)
 csvout(OUT/'dataset_provenance.csv',prov)
 js(OUT/'census_summary.json',{'all_saved_nodes':len(full),'unique_eligible_nodes':len(candidates),
     'per_dataset':{d:sum(r['Dataset']==d for r in candidates) for d in CFG['datasets']},'ordered_attempts':len(chosen),
     'candidate_census_sha256':sha(OUT/'complete_candidate_node_census.csv'),
     'selection_frozen_before_cost_analysis':True})
 print(json.dumps({'status':'PASS','saved':len(full),'unique':len(candidates),'attempts':len(chosen)}))
if __name__=='__main__':main()
