#!/usr/bin/env python3
"""Compare fresh scene processes, persistent workers, and cold/warm scoped builds.

All outputs go into .flow/benchmarks; original artifact bytes are read only.
Run from the installed project's environment, with identical explicit CPU affinity.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

from flow_cad.config import load_flow_config
from flow_cad.sdk import load_manifest, dump_manifest, ArtifactSpec
from flow_cad.registry import sync_project
from flow_cad.build.service import plan_scoped_part_build
from flow_cad.build.worker import run_scoped_part_build
from flow_cad.workers.pool import CadWorkerPool


class Context:
    def checkpoint(self): pass
    def report(self,*args): pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--part',required=True)
    parser.add_argument('--scene',action='append',default=[])
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    project=args.project.resolve()
    manifest=load_manifest(project/'flowcad.project.yaml')
    root=project/'.flow/benchmarks'/args.output.stem
    root.mkdir(parents=True,exist_ok=True)
    part=next(p for p in manifest.parts if p.key==args.part)
    selected=replace(part,artifacts=(ArtifactSpec('step','exports/step/part.step'),ArtifactSpec('stl','exports/stl/part.stl')))
    subset=replace(manifest,parts=(selected,),assemblies=())
    (root/'flowcad.project.yaml').write_text(dump_manifest(subset))
    # Preserve actual product source/provenance roots when generators use __file__.
    package=project.joinpath(*manifest.python_package.split('.'))
    link=root/manifest.python_package
    if package.is_dir() and not link.exists(): link.symlink_to(package,target_is_directory=True)
    sync_project(root)
    config=load_flow_config(project)
    config=replace(config,cad=replace(config.cad,workers=2,native_threads=1))
    result={'project':manifest.project_id,'part':part.key,'affinity':sorted(os.sched_getaffinity(0)),
            'worker_settings':vars(config.cad),'builds':[],'scenes':{}}
    pool=CadWorkerPool(root,config)
    try:
        plan=plan_scoped_part_build(root,subset,selected)
        for _ in range(2):
            started=time.perf_counter()
            output=run_scoped_part_build(plan,Context(),pool=pool)
            result['builds'].append({**output,'wall_seconds':time.perf_counter()-started})
    finally:
        pool.close()
    paths=[]
    for key in args.scene:
        record=next(p for p in manifest.parts if p.key==key)
        paths.append(project/next(a.path for a in record.artifacts if a.kind=='step'))
    if paths:
        started=time.perf_counter()
        for index,path in enumerate(paths):
            with (root/f'fresh-{index}.log').open('w') as log:
                subprocess.run([sys.executable,'-m','flow_cad.viewer.scene_export',str(path),str(root/f'fresh-{index}.glb')],
                    check=True,stdout=log,stderr=log,env={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1'})
        result['scenes']['fresh_serial_seconds']=time.perf_counter()-started
        pool=CadWorkerPool(root,config)
        try:
            for label in ('cold_pool','warm_pool'):
                started=time.perf_counter()
                with ThreadPoolExecutor(2) as executor:
                    tasks=[executor.submit(pool.run,'scene',(path,root/f'{label}-{i}.glb'),Context()) for i,path in enumerate(paths)]
                    for task in tasks: task.result()
                result['scenes'][label+'_seconds']=time.perf_counter()-started
            result['scenes']['worker_pids']=[w.process.pid for w in pool._workers if w.process]
        finally:
            pool.close()
    result['children_peak_rss_kib']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'build_seconds':[b['wall_seconds'] for b in result['builds']],'scenes':result['scenes']}))


if __name__=='__main__':
    main()
