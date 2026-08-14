#!/usr/bin/env python
# ============================================================
# Ensemble 经验统计预计算(板块一 Dataset Exploration 的数据底座)
#
# 输入: /fs/ess/PAS0027/nyx/256/output 下前 400 个 member 的
#       Raw_plt256_00200/density.bin  (256^3, <f4, 原始密度 rho)
# 所有统计均在 log10(rho) 空间进行, 与现有管线的 logmean 基线一致。
#
# 输出(本目录下):
#   members.csv / members.json  member-wise 统计 + 3 个模拟参数
#   voxelwise/{mean,median,std,min,max,range,q05,q25,q75,q95}.bin
#                               逐体素统计场, 256^3 <f4, 与源数据同布局
#   meta.json                   数据说明
#
# 用法: python compute_stats.py  (约需 20-30 GB 顺序读, 峰值内存 ~12 GB)
# ============================================================
import os, re, json, time
import numpy as np
from concurrent.futures import ProcessPoolExecutor

SRC_ROOT = os.environ.get('NYX_SRC_ROOT', '/path/to/nyx/256/output')  # raw ensemble root (one <id>_<OmM>_<OmB>_<h>/ dir per member)
OUT_ROOT = os.path.dirname(os.path.abspath(__file__))
VOX_DIR = os.path.join(OUT_ROOT, 'voxelwise')
# 430 = 与 evidential INR 的划分对齐: train 0-149 + unused 150-199 +
#       calibration 200-399 + test 400-429 (Evidential_INR/fg_*_nyx_evidential*.sh)
N_MEMBERS = 430
DIM = 256
NVOX = DIM ** 3
DTYPE = '<f4'
TIMESTEP = 'Raw_plt256_00200'
QS = [0.05, 0.25, 0.5, 0.75, 0.95]

# 逐体素统计: 每次处理一个 z-slab, 需要把 400 个 member 的该 slab 同时载入
SLAB = 16                        # 每 slab 16 层 -> (400,16,256,256) f4 = 1.6 GB
N_WORKERS_VOX = 6
N_WORKERS_MEM = 8

VOX_FIELDS = ['mean', 'median', 'std', 'min', 'max', 'range',
              'q05', 'q25', 'q75', 'q95']


def list_members():
    pat = re.compile(r'^(\d{4})_([\d.]+)_([\d.]+)_([\d.]+)$')
    dirs = sorted(os.listdir(SRC_ROOT))[:N_MEMBERS]
    members = []
    for d in dirs:
        m = pat.match(d)
        members.append({
            'id': int(m.group(1)),
            'dir': d,
            'OmM': float(m.group(2)),
            'OmB': float(m.group(3)),
            'h': float(m.group(4)),
            'path': os.path.join(SRC_ROOT, d, TIMESTEP, 'density.bin'),
        })
    return members


# ---------- Pass 1: member-wise ----------
def member_stats(mem):
    a = np.log10(np.fromfile(mem['path'], dtype=DTYPE))
    q05, q25, med, q75, q95 = np.quantile(a, QS)
    return {
        'id': mem['id'], 'dir': mem['dir'],
        'OmM': mem['OmM'], 'OmB': mem['OmB'], 'h': mem['h'],
        'mean': float(a.mean()), 'median': float(med),
        'std': float(a.std()), 'min': float(a.min()), 'max': float(a.max()),
        'range': float(a.max() - a.min()),
        'q05': float(q05), 'q25': float(q25),
        'q75': float(q75), 'q95': float(q95),
    }


def run_memberwise(members):
    t0 = time.time()
    with ProcessPoolExecutor(N_WORKERS_MEM) as ex:
        rows = list(ex.map(member_stats, members, chunksize=8))
    rows.sort(key=lambda r: r['id'])

    cols = ['id', 'dir', 'OmM', 'OmB', 'h', 'mean', 'median', 'std',
            'min', 'max', 'range', 'q05', 'q25', 'q75', 'q95']
    with open(os.path.join(OUT_ROOT, 'members.csv'), 'w') as f:
        f.write(','.join(cols) + '\n')
        for r in rows:
            f.write(','.join(str(r[c]) for c in cols) + '\n')
    with open(os.path.join(OUT_ROOT, 'members.json'), 'w') as f:
        json.dump(rows, f, indent=1)
    print(f'[memberwise] {len(rows)} members done in {time.time()-t0:.1f}s',
          flush=True)


# ---------- Pass 2: voxel-wise ----------
def voxel_slab(args):
    z0, paths = args
    z1 = z0 + SLAB
    buf = np.empty((len(paths), SLAB, DIM, DIM), dtype=np.float32)
    for i, p in enumerate(paths):
        mm = np.memmap(p, dtype=DTYPE, mode='r', shape=(DIM, DIM, DIM))
        buf[i] = mm[z0:z1]
        del mm
    np.log10(buf, out=buf)

    out = {'mean': buf.mean(axis=0, dtype=np.float64).astype(np.float32),
           'std':  buf.std(axis=0, dtype=np.float64).astype(np.float32)}
    buf.sort(axis=0)                       # 排序后所有分位数都是 O(1) 取值
    out['min'] = buf[0].copy()
    out['max'] = buf[-1].copy()
    out['range'] = out['max'] - out['min']
    n = len(paths)
    for name, q in zip(['q05', 'q25', 'median', 'q75', 'q95'], QS):
        # 线性插值分位数(与 np.quantile 默认 'linear' 一致)
        pos = q * (n - 1)
        lo, frac = int(np.floor(pos)), pos - int(np.floor(pos))
        out[name] = ((1 - frac) * buf[lo] + frac * buf[min(lo + 1, n - 1)]
                     ).astype(np.float32)

    # 各 worker 写各自的 z 区间, 字节范围互不重叠
    for name in VOX_FIELDS:
        mm = np.memmap(os.path.join(VOX_DIR, name + '.bin'), dtype=DTYPE,
                       mode='r+', shape=(DIM, DIM, DIM))
        mm[z0:z1] = out[name]
        mm.flush()
        del mm
    return z0


def run_voxelwise(members):
    t0 = time.time()
    os.makedirs(VOX_DIR, exist_ok=True)
    for name in VOX_FIELDS:                # 预分配输出文件
        p = os.path.join(VOX_DIR, name + '.bin')
        if not os.path.isfile(p) or os.path.getsize(p) != NVOX * 4:
            np.zeros(NVOX, dtype=DTYPE).tofile(p)

    paths = [m['path'] for m in members]
    tasks = [(z0, paths) for z0 in range(0, DIM, SLAB)]
    with ProcessPoolExecutor(N_WORKERS_VOX) as ex:
        for z0 in ex.map(voxel_slab, tasks):
            print(f'[voxelwise] slab z={z0}-{z0+SLAB} done '
                  f'({time.time()-t0:.0f}s elapsed)', flush=True)
    print(f'[voxelwise] all {len(tasks)} slabs done in {time.time()-t0:.1f}s',
          flush=True)


def write_meta(members):
    meta = {
        'description': f'Empirical statistics of the first {len(members)} Nyx '
                       'ensemble members (aligned with the evidential INR '
                       'splits: train 0-149, calibration 200-399, test '
                       '400-429), computed in log10(density) space.',
        'source_root': SRC_ROOT,
        'timestep': TIMESTEP,
        'n_members': len(members),
        'member_ids': [members[0]['id'], members[-1]['id']],
        'dims': [DIM, DIM, DIM],
        'dtype': 'float32 little-endian, same C-order layout as source '
                 'density.bin',
        'value_space': 'log10(rho)',
        'quantile_method': 'linear interpolation (np.quantile default)',
        'params': {'OmM': 'Omega_m', 'OmB': 'Omega_b', 'h': 'Hubble'},
        'files': {
            'members.csv/json': 'member-wise stats + simulation params',
            'voxelwise/*.bin': VOX_FIELDS,
        },
    }
    with open(os.path.join(OUT_ROOT, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)


if __name__ == '__main__':
    members = list_members()
    assert len(members) == N_MEMBERS
    print(f'{len(members)} members: {members[0]["dir"]} .. '
          f'{members[-1]["dir"]}', flush=True)
    run_memberwise(members)
    run_voxelwise(members)
    write_meta(members)
    print('ALL DONE', flush=True)
