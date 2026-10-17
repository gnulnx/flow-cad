"""CAD imports must not wedge concurrent journal connection lifetimes."""
import subprocess
import sys


def test_journal_reads_after_cad_import(tmp_path):
    script = '''
import flow_cad.main
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from flow_cad.jobs.store import JobStore
import sys
store = JobStore(Path(sys.argv[1]))
job, _ = store.create(request_id="stress", kind="test", payload={})
def read(_):
    for i in range(500):
        assert store.get(job.job_id).job_id == job.job_id
with ThreadPoolExecutor(4) as executor:
    list(executor.map(read, range(4)))
'''
    subprocess.run([sys.executable, '-c', script, str(tmp_path)], check=True, timeout=45)
