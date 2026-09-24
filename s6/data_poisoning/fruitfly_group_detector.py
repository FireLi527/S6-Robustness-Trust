"""Candidate-only CLIP label anomaly signals with specimen-disjoint reference folds."""
import hashlib
from dataclasses import dataclass
import numpy as np
from sklearn.linear_model import LogisticRegression

@dataclass(frozen=True)
class GroupedInput:
    sample_id: str
    sha256: str
    assigned_label: str
    group_id: str

def fold_indices(groups, n_splits=5, seed=2026):
    groups=np.asarray(groups)
    unique=np.array(sorted(set(groups.tolist())))
    if len(unique)<n_splits:raise ValueError('Insufficient independent specimen groups')
    np.random.default_rng(seed).shuffle(unique)
    for part in np.array_split(unique,n_splits):
        held=np.isin(groups,part)
        train=np.flatnonzero(~held);test=np.flatnonzero(held)
        assert not set(groups[train]) & set(groups[test])
        yield train,test

def group_weights(groups):
    counts={g:int(np.sum(groups==g)) for g in set(groups.tolist())}
    weights=np.array([1/counts[g] for g in groups])
    return weights/weights.mean()

def signals(records,embeddings,c=1.):
    if len({r.sample_id for r in records})!=len(records) or len({r.sha256 for r in records})!=len(records):
        raise ValueError('Duplicate candidate ID or image')
    features=np.stack([embeddings[r.sha256] for r in records]).astype(np.float64)
    if not np.isfinite(features).all() or np.any(np.linalg.norm(features,axis=1)==0):raise ValueError('Invalid embeddings')
    features/=np.linalg.norm(features,axis=1,keepdims=True)
    labels=np.array([r.assigned_label for r in records]);groups=np.array([r.group_id for r in records])
    output=np.zeros((len(records),3));folds=np.full(len(records),-1)
    for fold,(reference,held) in enumerate(fold_indices(groups)):
        x=features[reference];y=labels[reference];g=groups[reference];q=features[held]
        weights=group_weights(g)
        if len(set(y))<2:raise ValueError('Reference fold has fewer than two candidate classes')
        model=LogisticRegression(C=c,class_weight='balanced',max_iter=2000,random_state=2026)
        model.fit(x,y,sample_weight=weights)
        probs=model.predict_proba(q);class_index={v:i for i,v in enumerate(model.classes_)}
        similarities=q@x.T
        # One nearest image per reference specimen. Multiple views cannot dominate a vote.
        ordered_groups=sorted(set(g.tolist()))
        group_positions=[np.flatnonzero(g==value) for value in ordered_groups]
        for local,index in enumerate(held):
            representatives=np.array([pos[np.argmax(similarities[local,pos])] for pos in group_positions])
            selected=representatives[np.argsort(-similarities[local,representatives])[:15]]
            output[index,0]=1-np.mean(y[selected]==labels[index])
            output[index,1]=1-probs[local,class_index[labels[index]]] if labels[index] in class_index else 1.
        # Reference-only candidate-class centroids and distance calibration.
        for label in set(labels[held].tolist()):
            mask=y==label;indices=held[labels[held]==label]
            if not mask.any():output[indices,2]=1.;continue
            centroid=np.average(x[mask],axis=0,weights=weights[mask])
            distances=np.linalg.norm(x[mask]-centroid,axis=1)
            mean=np.average(distances,weights=weights[mask])
            std=max(float(np.sqrt(np.average((distances-mean)**2,weights=weights[mask]))),1e-6)
            z=(np.linalg.norm(features[indices]-centroid,axis=1)-mean)/std
            output[indices,2]=np.clip(z/3,0,1)
        folds[held]=fold
    if np.any(folds<0):raise ValueError('Missing held-out predictions')
    return output,folds

def group_id(filename):
    # Opaque ID: filename encodes class, so it must never be a learned feature.
    return hashlib.sha256(filename[:9].encode()).hexdigest()

def decisions(records,matrix,weights,threshold):
    risk=matrix@np.asarray(weights)
    return {r.sample_id:dict(decision='REVIEW' if score>=threshold else 'ALLOW',risk_score=float(score),
             signals=[float(v) for v in matrix[i]]) for i,(r,score) in enumerate(zip(records,risk))}
