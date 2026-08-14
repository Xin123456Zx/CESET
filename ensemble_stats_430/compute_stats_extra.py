#!/usr/bin/env python
# ============================================================
# Ensemble 统计增量计算 — 在 compute_stats.py 产出的基础上追加:
#
# member-wise (追加进 members.csv/json):
#   iqr, w90(=q95-q05), skew, kurt, grad_mean(平均梯度模长),
#   rmse_to_mean, corr_to_mean(与 ensemble 均值场的 RMSE / Pearson r),
#   dist_mean(到其他成员的平均 L2 距离),
#   outlier_maha((mean,std) 空间 Mahalanobis 距离, 与 90% 椭圆同一定义),
#   outlier_struct(dist_mean 的稳健 z 分数, 结构性离群)
#
# voxel-wise (voxelwise/ 下追加):
#   iqr.bin, w90.bin, skew.bin, kurt.bin, mad.bin, entropy.bin
#
# ensemble 级:
#   dist_matrix.bin   400x400 <f4  成员间 L2 距离(基于逐体素 anomaly, 等于原场距离)
#   corr_matrix.bin   400x400 <f4  成员 anomaly 场之间的 Pearson 相关
#   histograms.json   每成员 64-bin log10 直方图 + 全局直方图
#   sensitivity.json  参数 x 响应 的 Spearman rho / p-value
#   ensemble_summary.json  散点图辅助: 均值十字线 / 协方差 / 90% 椭圆 / 全局范围
#
# 依赖 compute_stats.py 已生成: members.json, voxelwise/{mean,std,median,q*}.bin
# ============================================================
import os, json, time
import numpy as np

os.environ.setdefault('OMP_NUM_THREADS', '2')   # 每 worker 限 BLAS 线程, 对 login 节点友好
from concurrent.futures import ProcessPoolExecutor
from scipy.stats import spearmanr, skew as sp_skew, kurtosis as sp_kurt
from scipy.stats.distributions import chi2

OUT_ROOT = os.path.dirname(os.path.abspath(__file__))
VOX_DIR = os.path.join(OUT_ROOT, 'voxelwise')
DIM = 256
NVOX = DIM ** 3
DTYPE = '<f4'
SLAB = 16
N_WORKERS_VOX = 6
N_WORKERS_MEM = 8
N_HIST_BINS = 64        # 成员直方图与 voxel-wise entropy 共用同一套 bin
EPS_STD = 1e-6          # voxel std 低于此值时 skew/kurt 置 0


def load_members():
    with open(os.path.join(OUT_ROOT, 'members.json')) as f:
        return json.load(f)


# ---------- Pass A: 逐成员(整场读入) ----------
def member_extra(args):
    mem, gmin, gmax = args
    a = np.log10(np.fromfile(mem['path'], dtype=DTYPE)).astype(np.float32)
    hist, _ = np.histogram(a, bins=N_HIST_BINS, range=(gmin, gmax))
    vol = a.reshape(DIM, DIM, DIM)
    gx, gy, gz = np.gradient(vol)
    grad_mean = float(np.sqrt(gx**2 + gy**2 + gz**2, dtype=np.float32).mean())
    return {
        'id': mem['id'],
        'skew': float(sp_skew(a)),
        'kurt': float(sp_kurt(a)),          # Fisher 定义, 正态分布 = 0
        'grad_mean': grad_mean,
        'hist': hist.tolist(),
    }


# ---------- Pass B: 逐 slab(复用已有 mean/std/median 场) ----------
def read_vox(name, z0, z1):
    mm = np.memmap(os.path.join(VOX_DIR, name + '.bin'), dtype=DTYPE,
                   mode='r', shape=(DIM, DIM, DIM))
    out = np.array(mm[z0:z1])
    del mm
    return out


def write_vox(name, z0, arr):
    mm = np.memmap(os.path.join(VOX_DIR, name + '.bin'), dtype=DTYPE,
                   mode='r+', shape=(DIM, DIM, DIM))
    mm[z0:z0 + arr.shape[0]] = arr
    mm.flush()
    del mm


def voxel_slab_extra(args):
    z0, paths, gmin, gmax = args
    z1 = z0 + SLAB
    n = len(paths)
    buf = np.empty((n, SLAB, DIM, DIM), dtype=np.float32)
    for i, p in enumerate(paths):
        mm = np.memmap(p, dtype=DTYPE, mode='r', shape=(DIM, DIM, DIM))
        buf[i] = mm[z0:z1]
        del mm
    np.log10(buf, out=buf)

    m = read_vox('mean', z0, z1)            # 复用第一遍算好的场
    s = read_vox('std', z0, z1)
    med = read_vox('median', z0, z1)

    # --- 逐体素 skew / kurt(围绕已有 mean 的三/四阶矩) ---
    d = buf - m[None]
    d2 = d * d
    m3 = (d2 * d).mean(axis=0, dtype=np.float64)
    m4 = (d2 * d2).mean(axis=0, dtype=np.float64)
    safe = np.maximum(s.astype(np.float64), EPS_STD)
    skew_v = np.where(s > EPS_STD, m3 / safe**3, 0.0).astype(np.float32)
    kurt_v = np.where(s > EPS_STD, m4 / safe**4 - 3.0, 0.0).astype(np.float32)
    del d2, m3, m4

    # --- MAD(围绕已有 median) ---
    mad = np.median(np.abs(buf - med[None]), axis=0).astype(np.float32)

    # --- 逐体素 entropy + (顺便校验用的)全局直方图, 共用 bin ---
    scale = N_HIST_BINS / (gmax - gmin)
    idx = np.clip(((buf - gmin) * scale).astype(np.int16), 0, N_HIST_BINS - 1)
    ent = np.zeros((SLAB, DIM, DIM), dtype=np.float32)
    for b in range(N_HIST_BINS):
        c = (idx == b).sum(axis=0)
        p = c.astype(np.float32) / n
        nz = p > 0
        ent[nz] -= (p[nz] * np.log(p[nz]))
    del idx

    write_vox('skew', z0, skew_v)
    write_vox('kurt', z0, kurt_v)
    write_vox('mad', z0, mad)
    write_vox('entropy', z0, ent)

    # --- 成员间关系的 slab 部分和(anomaly = 减去 voxel-wise mean) ---
    # 平移不改变成员间距离; anomaly 相关是结构相似度的标准度量
    a = d.reshape(n, -1)                    # d = buf - mean, 上面已算
    Gc = (a @ a.T).astype(np.float64)       # (400,400) centered Gram
    a_sum = a.sum(axis=1, dtype=np.float64)
    am = (a @ m.reshape(-1).astype(np.float32)).astype(np.float64)
    m_sum = float(m.sum(dtype=np.float64))
    m_sq = float((m.astype(np.float64)**2).sum())
    return z0, Gc, a_sum, am, m_sum, m_sq


def run():
    t0 = time.time()
    members = load_members()
    n = len(members)
    src_root, timestep = None, None
    with open(os.path.join(OUT_ROOT, 'meta.json')) as f:
        meta = json.load(f)
    src_root, timestep = meta['source_root'], meta['timestep']
    for mem in members:
        mem['path'] = os.path.join(src_root, mem['dir'], timestep,
                                   'density.bin')

    gmin = min(mem['min'] for mem in members)
    gmax = max(mem['max'] for mem in members)
    print(f'global log10 range: [{gmin:.4f}, {gmax:.4f}]', flush=True)

    # ---- Pass A ----
    with ProcessPoolExecutor(N_WORKERS_MEM) as ex:
        rows = list(ex.map(member_extra, [(m, gmin, gmax) for m in members],
                           chunksize=8))
    rows.sort(key=lambda r: r['id'])
    print(f'[pass A] member skew/kurt/grad/hist done in '
          f'{time.time()-t0:.1f}s', flush=True)

    # ---- Pass B ----
    for name in ['skew', 'kurt', 'mad', 'entropy']:
        p = os.path.join(VOX_DIR, name + '.bin')
        if not os.path.isfile(p) or os.path.getsize(p) != NVOX * 4:
            np.zeros(NVOX, dtype=DTYPE).tofile(p)
    paths = [m['path'] for m in members]
    tasks = [(z0, paths, gmin, gmax) for z0 in range(0, DIM, SLAB)]
    Gc = np.zeros((n, n))
    a_sum = np.zeros(n)
    am = np.zeros(n)
    m_sum = m_sq = 0.0
    with ProcessPoolExecutor(N_WORKERS_VOX) as ex:
        for z0, Gc_p, as_p, am_p, ms_p, mq_p in ex.map(voxel_slab_extra,
                                                       tasks):
            Gc += Gc_p; a_sum += as_p; am += am_p
            m_sum += ms_p; m_sq += mq_p
            print(f'[pass B] slab z={z0} done ({time.time()-t0:.0f}s)',
                  flush=True)

    # ---- voxel-wise 派生场: iqr / w90 ----
    for out_name, hi, lo in [('iqr', 'q75', 'q25'), ('w90', 'q95', 'q05')]:
        h = np.fromfile(os.path.join(VOX_DIR, hi + '.bin'), dtype=DTYPE)
        l = np.fromfile(os.path.join(VOX_DIR, lo + '.bin'), dtype=DTYPE)
        (h - l).tofile(os.path.join(VOX_DIR, out_name + '.bin'))

    # ---- 成员间矩阵 ----
    V = float(NVOX)
    diag = np.diag(Gc)
    dist2 = diag[:, None] - 2 * Gc + diag[None, :]
    dist = np.sqrt(np.maximum(dist2, 0)).astype(np.float32)
    dist.tofile(os.path.join(OUT_ROOT, 'dist_matrix.bin'))

    abar = a_sum / V
    var_a = np.maximum(diag / V - abar**2, 1e-20)
    cov_a = Gc / V - np.outer(abar, abar)
    corr = (cov_a / np.sqrt(np.outer(var_a, var_a))).astype(np.float32)
    corr.tofile(os.path.join(OUT_ROOT, 'corr_matrix.bin'))

    # 与 ensemble 均值场的关系: x_i = a_i + m
    m_mean = m_sum / V
    var_m = m_sq / V - m_mean**2
    cov_xm = am / V - abar * m_mean + var_m          # Cov(x_i, m)
    var_x = diag / V + 2 * am / V + m_sq / V \
        - (abar + m_mean)**2                          # Var(x_i)
    corr_to_mean = cov_xm / np.sqrt(np.maximum(var_x, 1e-20) * var_m)
    rmse_to_mean = np.sqrt(diag / V)

    # ---- 离群分数 ----
    np.fill_diagonal(dist2, np.nan)
    dist_mean = np.sqrt(np.nanmean(dist2, axis=1))
    dmed = np.median(dist_mean)
    dmad = np.median(np.abs(dist_mean - dmed)) * 1.4826
    outlier_struct = (dist_mean - dmed) / max(dmad, 1e-12)

    ms = np.array([[mem['mean'], mem['std']] for mem in members])
    center = ms.mean(axis=0)
    cov = np.cov(ms.T)
    cinv = np.linalg.inv(cov)
    diff = ms - center
    outlier_maha = np.sqrt(np.einsum('ij,jk,ik->i', diff, cinv, diff))

    # ---- 合并回 members.csv / json ----
    for i, mem in enumerate(members):
        r = rows[i]
        assert r['id'] == mem['id']
        mem['iqr'] = mem['q75'] - mem['q25']
        mem['w90'] = mem['q95'] - mem['q05']
        mem['skew'] = r['skew']
        mem['kurt'] = r['kurt']
        mem['grad_mean'] = r['grad_mean']
        mem['rmse_to_mean'] = float(rmse_to_mean[i])
        mem['corr_to_mean'] = float(corr_to_mean[i])
        mem['dist_mean'] = float(dist_mean[i])
        mem['outlier_struct'] = float(outlier_struct[i])
        mem['outlier_maha'] = float(outlier_maha[i])
        mem.pop('path', None)

    cols = ['id', 'dir', 'OmM', 'OmB', 'h', 'mean', 'median', 'std',
            'min', 'max', 'range', 'q05', 'q25', 'q75', 'q95',
            'iqr', 'w90', 'skew', 'kurt', 'grad_mean',
            'rmse_to_mean', 'corr_to_mean', 'dist_mean',
            'outlier_struct', 'outlier_maha']
    with open(os.path.join(OUT_ROOT, 'members.csv'), 'w') as f:
        f.write(','.join(cols) + '\n')
        for mem in members:
            f.write(','.join(str(mem[c]) for c in cols) + '\n')
    with open(os.path.join(OUT_ROOT, 'members.json'), 'w') as f:
        json.dump(members, f, indent=1)

    # ---- histograms.json ----
    edges = np.linspace(gmin, gmax, N_HIST_BINS + 1)
    counts = [r['hist'] for r in rows]
    with open(os.path.join(OUT_ROOT, 'histograms.json'), 'w') as f:
        json.dump({'bin_edges': edges.tolist(),
                   'value_space': 'log10(rho)',
                   'member_ids': [mem['id'] for mem in members],
                   'counts': counts,
                   'global_counts': np.array(counts).sum(axis=0).tolist()},
                  f)

    # ---- sensitivity.json (Spearman) ----
    params = ['OmM', 'OmB', 'h']
    responses = ['mean', 'median', 'std', 'range', 'iqr', 'w90',
                 'skew', 'kurt', 'grad_mean', 'rmse_to_mean',
                 'corr_to_mean', 'dist_mean', 'outlier_struct',
                 'outlier_maha']
    sens = {}
    for p in params:
        pv = [mem[p] for mem in members]
        sens[p] = {}
        for resp in responses:
            rho, pval = spearmanr(pv, [mem[resp] for mem in members])
            sens[p][resp] = {'rho': float(rho), 'p': float(pval)}
    with open(os.path.join(OUT_ROOT, 'sensitivity.json'), 'w') as f:
        json.dump({'method': 'Spearman rank correlation, n=%d' % n,
                   'params': params, 'responses': responses,
                   'table': sens}, f, indent=1)

    # ---- ensemble_summary.json(散点图辅助元素) ----
    evals, evecs = np.linalg.eigh(cov)
    k90 = float(np.sqrt(chi2.ppf(0.90, df=2)))
    order = np.argsort(evals)[::-1]
    evals, evecs = evals[order], evecs[:, order]
    with open(os.path.join(OUT_ROOT, 'ensemble_summary.json'), 'w') as f:
        json.dump({
            'n_members': n,
            'global_log10_range': [gmin, gmax],
            'mean_of_member_means': float(center[0]),   # 散点图竖线
            'mean_of_member_stds': float(center[1]),    # 散点图横线
            'mean_std_cov': cov.tolist(),
            'ellipse90': {                              # 90% 高斯椭圆
                'center': center.tolist(),
                'semi_axes': (k90 * np.sqrt(evals)).tolist(),
                'angle_deg': float(np.degrees(
                    np.arctan2(evecs[1, 0], evecs[0, 0]))),
                'note': 'Mahalanobis dist <= %.4f' % k90,
            },
            'outlier_maha_thresh90': k90,
        }, f, indent=1)

    # ---- meta.json 追加 ----
    meta['files']['voxelwise/*.bin'] = sorted(
        fn[:-4] for fn in os.listdir(VOX_DIR) if fn.endswith('.bin'))
    meta['files'].update({
        'dist_matrix.bin': '400x400 <f4, member pairwise L2 distance '
                           '(log10 space)',
        'corr_matrix.bin': '400x400 <f4, Pearson corr of anomaly fields '
                           '(member - voxelwise mean)',
        'histograms.json': 'per-member & global 64-bin histograms',
        'sensitivity.json': 'Spearman rho/p, params x responses',
        'ensemble_summary.json': 'scatter helpers: crosshair lines, cov, '
                                 '90% ellipse',
    })
    meta['definitions'] = {
        'skew/kurt': 'standardized 3rd / excess 4th moment (Fisher)',
        'mad': 'median absolute deviation around voxel-wise median',
        'entropy': 'Shannon entropy (nats) of %d-bin histogram over global '
                   'log10 range' % N_HIST_BINS,
        'grad_mean': 'spatial mean of gradient magnitude (np.gradient)',
        'outlier_maha': 'Mahalanobis distance in (mean,std) plane; '
                        '>%.3f = outside 90%% Gaussian ellipse' % k90,
        'outlier_struct': 'robust z-score of mean L2 distance to all other '
                          'members',
        'w90': 'q95 - q05', 'iqr': 'q75 - q25',
    }
    with open(os.path.join(OUT_ROOT, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)

    print(f'ALL EXTRA DONE in {time.time()-t0:.1f}s', flush=True)


if __name__ == '__main__':
    run()
