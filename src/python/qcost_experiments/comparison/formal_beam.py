"""Original threshold-aware prefix trie from QMF-Motivation-Study/experiments/search_worker.py."""

def act(a):return f'{a.axis}:{float(a.threshold).hex()}'
def make_trie(u):
 children=[{}];mass=[0.];terminal={}
 for i,(plan,prob) in enumerate(zip(u.configurations,u.probabilities)):
  state=0;mass[0]+=float(prob)
  for step in plan.actions:
   token=act(step.action)
   if token not in children[state]:children[state][token]=len(children);children.append({});mass.append(0.)
   state=children[state][token];mass[state]+=float(prob)
  assert state not in terminal
  terminal[state]=i
 return children,mass,terminal
def beam(trie,costs,width):
 children,mass,terminal=trie;front=[(0,())];expanded=0
 while not all(i in terminal for i,_ in front):
  candidates=[]
  for i,prefix in front:
   for token,child in children[i].items():candidates.append((child,prefix+(token,)));expanded+=1
  front=sorted(candidates,key=lambda x:(-mass[x[0]],x[1]))[:width]
 ids=[terminal[i] for i,_ in front];index=min(ids,key=lambda i:costs[i])
 return index,len(ids),expanded
