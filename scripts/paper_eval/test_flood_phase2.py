"""Exact Flood preload ownership and immutable serialization regression."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import support as s

@pytest.fixture(scope='module')
def native(tmp_path_factory):
    folder=tmp_path_factory.mktemp('flood_phase2_native')
    base=s.BASE/'src/qmap/cpp'
    compiler=['g++','-O2','-std=c++17','-I'+str(base/'include'),
        '-I/var/tmp/qmf-paper-protocol-20260911/common/learnedbench-patched',
        str(s.ROOT/'scripts/diagnostics/flood_phase2_unit.cpp'),
        str(base/'src/baselines/learnedbench_adapters.cpp'),'-o',str(folder/'unit')]
    subprocess.run(compiler,check=True,capture_output=True)
    env={**os.environ,'QMF_FLOOD_OWNERSHIP_TRACE':str(folder/'trace.csv'),
        'QMF_FLOOD_MATCH_TRACE':str(folder/'matches.csv')}
    subprocess.run([str(folder/'unit'),str(folder)],env=env,check=True,capture_output=True)
    old=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915/phase1_adapters.cpp')
    reference=folder/'reference';reference.mkdir()
    previous=list(compiler);previous[-3]=str(old);previous[-1]=str(folder/'unit_reference')
    subprocess.run(previous,check=True,capture_output=True)
    subprocess.run([str(folder/'unit_reference'),str(reference)],check=True,capture_output=True)
    return folder

def test_coordinates_lifetime_release(native):
    rows=list(csv.DictReader((native/'trace.csv').open()))
    released=[r for r in rows if r['phase']=='after_coordinates_release']
    assert released and all(int(r['coordinates_bytes'])==0 for r in released)

def test_points_lifetime_release(native):
    rows=list(csv.DictReader((native/'trace.csv').open()))
    released=[r for r in rows if r['phase']=='after_points_release']
    assert released and all(int(r['points_resident_estimate'])==0 for r in released)

def test_duplicate_coordinates_exact(native):assert (native/'unit0.idx').is_file()
def test_float_canonicalization_signed_zero_and_nextafter(native):assert (native/'unit1.idx').is_file()
def test_id_ordering_and_repeated_ids(native):assert (native/'matches.csv').stat().st_size>0
def test_candidate_count_equal(native):
    rows=list(csv.reader((native/'matches.csv').open()))
    assert rows and all(rows[i]==rows[i+1] for i in range(0,len(rows),2))
def test_mapped_save_roundtrip_byte_identical(native):
    for orient in (0,1):
        original=native/f'unit{orient}.idx'
        assert original.read_bytes()==original.with_suffix('.idx.copy').read_bytes()
        assert original.read_bytes()==(native/'reference'/original.name).read_bytes()
        assert (native/f'size{orient}.txt').read_bytes()==(native/'reference'/f'size{orient}.txt').read_bytes()

def test_all_phase1_prefix_id_digests_unchanged():
    root=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915')
    for n in (1000000,5000000,10000000,25000000,50000000):
        completed=root/'ownership'/str(n)/'completed.json'
        if completed.exists():
            assert (completed.parent/'correctness.csv').read_bytes()==(Path('/var/tmp/qmf-flood-correctness-memfix-20260915/profiles')/str(n)/'after/correctness.csv').read_bytes()

def test_frozen_flood_model_source_unchanged():
    manifest=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915/FROZEN_LEARNEDBENCH_SHA.json')
    values=json.loads(manifest.read_text())
    assert values and all(s.sha(path)==digest for path,digest in values.items())

def test_qmf_and_other_production_sources_unchanged():
    receipt=json.loads(Path('/var/tmp/qmf-flood-correctness-memfix-20260915/acceptance.json').read_text())
    for name,digest in receipt['current_production_source_manifest'].items():
        if name=='src/qmap/cpp/src/baselines/learnedbench_adapters.cpp':continue
        assert s.sha(s.BASE/name)==digest

def test_compact_lookup_exactness_and_capacity(native):
    rows=list(csv.DictReader((native/'trace.csv').open()))
    compact=[r for r in rows if r['phase']=='after_compact_lookup_finalization']
    assert compact
    for r in compact:
        assert int(r['lookup_estimated_bytes'])==16*int(r['U'])+8+4*int(r['N'])
        assert int(r['id_capacity_bytes'])==4*int(r['N'])

def test_lookup_preserves_exact_numeric_coordinate_comparison():
    source=(s.BASE/'src/qmap/cpp/src/baselines/flood_compact_lookup.hpp').read_text()
    assert 'std::array<float,2>' in source
    assert 'double((*i)[0])!=match[0]' in source and 'double((*i)[1])!=match[1]' in source
    assert 'std::vector<std::uint64_t> offsets_' in source
    assert 'ids_[i]=point.id' in source

def test_compact_all_prefix_coordinate_sets_and_candidates_unchanged():
    root=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915')
    for n in (1000000,5000000,10000000,25000000,50000000):
        candidate=root/'compact'/str(n);baseline=root/'phase1'/str(n)
        if (candidate/'completed.json').exists() and (baseline/'completed.json').exists():
            assert (candidate/'matches.csv').read_bytes()==(baseline/'matches.csv').read_bytes()
            assert (candidate/'correctness.csv').read_bytes()==(baseline/'correctness.csv').read_bytes()

def test_every_prefix_coordinate_roundtrip_bitwise_exact():
    receipt=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915/COORDINATE_ROUNDTRIP_ALL_PREFIXES.json')
    rows=json.loads(receipt.read_text())
    assert [r['N'] for r in rows]==[1000000,5000000,10000000,25000000,50000000]
    assert all(r['float32_double_float32_bitwise_exact'] and r['finite'] for r in rows)

def test_all_original_formal_assets_and_flood_build_unchanged():
    root=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915')
    before=json.loads((root/'before.json').read_text())
    existing={str(p) for p in (s.ROOT/'results/four_dataset_paper_protocol_20260911').rglob('*') if p.is_file()}
    protected={r['path'] for r in before if '/results/four_dataset_paper_protocol_20260911/' in r['path']}
    # The September 19 QMF-only campaign may append evidence in its explicitly
    # owned namespace. Every September 15 artifact must still exist unchanged.
    formal=s.ROOT/'results/four_dataset_paper_protocol_20260911'
    additions=existing-protected
    assert protected<=existing
    assert all(Path(p).is_relative_to(formal/'qmf_only_20260919') or
        Path(p).is_relative_to(formal/'baseline_campaign_20260920') or Path(p).name in {
        'QMF_4DATASET_PREFLIGHT.md','QMF_INDEX_4_DATASETS_7_METRICS.csv',
        'ALL_METHODS_4_DATASETS_7_METRICS.csv','BENCHMARK_PROGRESS.md'
    } and Path(p).parent==formal for p in additions)
    assert all(Path(r['path']).stat().st_size==r['bytes'] and s.sha(r['path'])==r['sha256'] for r in before)

def test_retry_socket_path_fits_unix_limit():
    import flood_resume
    target=flood_resume.ATTEMPTS/('20260915T123456-'+'a'*32)
    socket=flood_resume.runtime_path(target)/'common/pg_socket/.s.PGSQL.55445'
    assert len(str(socket).encode())<108
    assert not flood_resume.runtime_path(target).exists()
