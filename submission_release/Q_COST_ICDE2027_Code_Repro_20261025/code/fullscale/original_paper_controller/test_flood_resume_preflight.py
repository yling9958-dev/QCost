"""Resume infrastructure only; every execution target is an isolated fixture."""
import errno
import fcntl
import json
import os
from pathlib import Path

import pytest
import flood_resume as f
import diagnose
import repair_geolife as repair
import run
from test_flood_correctness import flood_env, retry_env, bytes_under


def configure_preflight(monkeypatch):
    gate={'predicted_181m_peak_mib':13188.961152}
    state={'host_meminfo':{'MemAvailable':30*1024**3},'parent':{},'processes':[]}
    monkeypatch.setattr(f,'verify_gate',lambda:gate)
    monkeypatch.setattr(diagnose,'ownership',lambda *_:state)
    monkeypatch.setattr(repair,'stale_processes',lambda _:[])
    monkeypatch.setattr(f.o.cgroup_policy,'validate',lambda _:True)
    monkeypatch.setattr(f,'protected_files',lambda:{})
    monkeypatch.setattr(f,'latest_pass_attempt',lambda:None)
    (f.RUNTIME/'campaign.lock').touch()
    return state


def test_flood_resume_preflight_failure_logged(flood_env,monkeypatch,capsys):
    configure_preflight(monkeypatch)
    def fail():raise PermissionError(errno.EPERM,'fixture failure')
    monkeypatch.setattr(f,'new_attempt',fail)
    with pytest.raises(PermissionError):f.foreground()
    captured=capsys.readouterr()
    assert 'PREFLIGHT_STAGE = new_attempt' in captured.out
    assert 'PREFLIGHT_FAILED = new_attempt' in captured.err
    assert 'Traceback (most recent call last)' in captured.err
    assert 'PermissionError' in captured.err and 'elapsed_s=' in captured.err


def test_flood_resume_exfat_layout(flood_env,monkeypatch):
    target=f.new_attempt()
    before=bytes_under(f.FORMAL)
    symlink=Path.symlink_to
    def exfat(path,*args,**kwargs):
        if path.is_relative_to(target):raise PermissionError(errno.EPERM,'exFAT has no symlinks')
        return symlink(path,*args,**kwargs)
    monkeypatch.setattr(Path,'symlink_to',exfat)
    with f.isolated_output(target):
        assert json.loads((target/'runtime_path.json').read_text())['runtime_path']==str(f.runtime_path(target))
        assert not (target/'runtime').exists()
        assert (f.runtime_path(target)/'common/pg_data').is_symlink()
        with pytest.raises(RuntimeError,match='reexecution forbidden'):f.o.build_one()
    assert bytes_under(f.FORMAL)==before


def test_flood_resume_does_not_rebuild(flood_env,monkeypatch):
    target=f.new_attempt();calls=[]
    monkeypatch.setattr(f.o,'ensure_pg',lambda:None)
    monkeypatch.setattr(f.o,'cleanup_method',lambda *_:None)
    def stop(command,*args,**kwargs):
        calls.append(command[command.index('--phase')+1])
        raise f.o.Blocked('HOST_SAFETY_STOP','fixture only')
    monkeypatch.setattr(f.o,'monitor',stop)
    result=f.perform(target)
    assert calls==['correctness']
    assert result['Build_s']==112.318935022


def test_flood_resume_does_not_touch_pass_results(flood_env,monkeypatch):
    configure_preflight(monkeypatch)
    for name in ['QMF','PostGIS','LISA','Tsunami','LMSFC','BMTree']:
        path=f.FORMAL/'pass'/name;path.parent.mkdir(exist_ok=True)
        path.write_bytes(b'opaque PASS evidence\r\n')
    before=bytes_under(f.FORMAL)
    monkeypatch.setattr(f,'new_attempt',lambda:(_ for _ in ()).throw(RuntimeError('STOP before attempt')))
    with pytest.raises(RuntimeError,match='STOP before attempt'):f.foreground()
    assert bytes_under(f.FORMAL)==before


@pytest.mark.parametrize('failure',['none','safe','equivalence','prediction','policy','source_sha','tests'])
def test_flood_resume_gate_validation(tmp_path,monkeypatch,failure):
    monkeypatch.setattr(f,'AUDIT',tmp_path)
    source=tmp_path/'source';source.write_bytes(b'frozen')
    value={'safe_for_full_retry':True,'equivalence_pass':True,'predicted_181m_peak_mib':13188.961152,
           'tests_path':str(tmp_path/'tests.xml'),
           'memory_policy':[f.MEMORY_HIGH,f.MEMORY_MAX,f.MEMORY_SWAP_MAX,f.HOST_EMERGENCY_RESERVE],
           'source_files':{str(source):f.s.sha(source)},'runtime_files':{},'evidence_files':{}}
    if failure=='safe':value['safe_for_full_retry']=False
    if failure=='equivalence':value['equivalence_pass']=False
    if failure=='prediction':value['predicted_181m_peak_mib']=18433
    if failure=='policy':value['memory_policy'][-1]=0
    if failure=='source_sha':source.write_bytes(b'changed')
    monkeypatch.setattr(run,'passing_test_xml',lambda _:failure!='tests')
    calls=[];monkeypatch.setattr(f,'validate_build',lambda:calls.append('build verified'))
    (tmp_path/'acceptance.json').write_text(json.dumps(value))
    if failure=='none':
        assert f.verify_gate()==value and calls==['build verified']
    else:
        with pytest.raises(RuntimeError):f.verify_gate()
        assert calls==[]


def test_flood_resume_lock_validation(flood_env,monkeypatch,capsys):
    configure_preflight(monkeypatch)
    path=f.RUNTIME/'campaign.lock';inode=path.stat().st_ino
    monkeypatch.setattr(f,'new_attempt',lambda:pytest.fail('locked controller reached attempt'))
    with path.open('r') as holder:
        fcntl.flock(holder,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):f.foreground()
    assert path.stat().st_ino==inode
    assert 'PREFLIGHT_FAILED = lock' in capsys.readouterr().err


def test_flood_resume_stale_process_validation(flood_env,monkeypatch,capsys):
    configure_preflight(monkeypatch)
    monkeypatch.setattr(repair,'stale_processes',lambda _:[12345])
    monkeypatch.setattr(f,'new_attempt',lambda:pytest.fail('stale process reached attempt'))
    with pytest.raises(RuntimeError,match='Stale benchmark'):f.foreground()
    assert 'PREFLIGHT_FAILED = stale_processes' in capsys.readouterr().err


def test_flood_resume_systemd_environment(flood_env,monkeypatch,capsys):
    monkeypatch.setattr(f.report,'valid_method',lambda *_:False)
    monkeypatch.setattr(f,'verify_gate',lambda:{})
    monkeypatch.setattr(f.o,'props',lambda _: {})
    calls=[]
    monkeypatch.setattr(f.subprocess,'run',lambda cmd,**kw:calls.append(cmd))
    before=bytes_under(f.FORMAL)
    f.start()
    cmd=calls[0]
    assert cmd[:3]==['systemd-run','--user','--collect']
    for item in ['--setenv=PYTHONDONTWRITEBYTECODE=1','--setenv=OPENBLAS_NUM_THREADS=1','--setenv=OMP_NUM_THREADS=1']:
        assert item in cmd
    assert '--foreground'==cmd[-1]
    assert 'FLOOD_RESUME_LOG = ' in capsys.readouterr().out
    assert bytes_under(f.FORMAL)==before


def test_flood_resume_no_formal_write_before_attempt(flood_env,monkeypatch):
    configure_preflight(monkeypatch)
    before=bytes_under(f.FORMAL);attempts=bytes_under(f.ATTEMPTS) if f.ATTEMPTS.exists() else {}
    def fail():raise RuntimeError('bad gate')
    monkeypatch.setattr(f,'verify_gate',fail)
    monkeypatch.setattr(f,'new_attempt',lambda:pytest.fail('bad gate reached attempt'))
    with pytest.raises(RuntimeError,match='bad gate'):f.foreground()
    assert bytes_under(f.FORMAL)==before
    assert (bytes_under(f.ATTEMPTS) if f.ATTEMPTS.exists() else {})==attempts


def test_flood_resume_low_memory_wait_is_not_failure(flood_env,monkeypatch):
    state=configure_preflight(monkeypatch)
    state['host_meminfo']['MemAvailable']=1024**3
    calls=[]
    def sleep(seconds):
        calls.append(seconds);state['host_meminfo']['MemAvailable']=30*1024**3
    monkeypatch.setattr(f.time,'sleep',sleep)
    monkeypatch.setattr(f,'new_attempt',lambda:(_ for _ in ()).throw(RuntimeError('STOP before attempt')))
    with pytest.raises(RuntimeError,match='STOP before attempt'):f.foreground()
    assert calls==[10]
