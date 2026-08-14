import os
import re
import glob
import functools
import numpy as np
import vtk
import torch
import logging
from vtk.util import numpy_support
from collections import OrderedDict
from scipy.stats import t
from flask import Flask, jsonify, request

from inr_model import INR_FG_Evidential

app = Flask(__name__)
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

# Configure logging
logging.basicConfig(level=logging.ERROR)

# Output directory for generated vti files (frontend public, served statically by Vite)
save_dir = os.path.join(PROJECT_ROOT, "frontend", "public")
os.makedirs(save_dir, exist_ok=True)

# ---------------------------------------------------------------------------
# Surrogate model: Evidential INR-FG (training package: ../explorable-inr)
#   Input row = [x, y, z, OmM_n, OmB_n, h_n] (coordinates in [-1,1], parameters normalized to [0,1])
#   Per-point output NIG(gamma, v, alpha, beta)
#   pred(log10 rho) = gamma * data_range + dmin      -- directly the absolute log10 density, no baseline needed
# ---------------------------------------------------------------------------
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
if device.type != 'cuda':
    logging.error("CUDA unavailable: the INR evaluates 256^3 = 16.7M points per-voxel, which is very slow on CPU. Start the backend on a machine with an NVIDIA GPU.")

# Normalization ranges for the 3 physical parameters (same as model training: min + (max-min)*u)
min_max_nyx_param = [
    [0.12, 0.155],      # OmM
    [0.0215, 0.0235],   # OmB
    [0.55, 0.85],       # h
]

# log10(rho) normalization range (consistent with the Evidential_INR training/testing scripts)
NYX_DMIN = 8.77
NYX_DMAX = 12.80
NYX_RANGE = NYX_DMAX - NYX_DMIN     # 4.03
NYX_RES = 256

# INR architecture hyperparameters (for weights nyx_evidential_64_256_16_32_16, epoch 30, raw gamma head)
INR_WEIGHTS = os.path.join(BACKEND_DIR, "model", "nyx_inr_evidential_raw_30.pth")
INR_DIM3D, INR_DIM2D, INR_DIM1D = 64, 256, 16
INR_SPATIAL_FDIM, INR_PARAM_FDIM = 32, 16
INR_BATCH = 262144

# Conformal calibration correction fields Q_lo/Q_hi (precomputed on the Evidential_INR side, per-voxel normalized space)
cal_data_dir = os.environ.get(
    "INR_CALIBRATION_DIR",
    os.path.join(PROJECT_ROOT, "explorable-inr", "outputs"),
)
CAL_PREFIX = "nyx_evidential_64_256_16_32_16"   # raw gamma head

# In-memory cache of model forward outputs (gamma,v,alpha,beta): a full-field forward takes ~0.5s;
# cache the most recent parameter sets so view1 / view2 / calibration for the same parameters
# run the forward only once (each set is 4x256^3x4B ~= 268MB)
_NIG_CACHE_MAX = 3
_nig_cache = OrderedDict()


def normalize_param(param, min_max):
    """ Normalize input parameters to [0,1] """
    param = (param - np.array(min_max)[:, 0]) / (np.array(min_max)[:, 1] - np.array(min_max)[:, 0])
    return param


# Load the Evidential INR surrogate model
feature_grid_shape = np.concatenate((
    np.ones(3, dtype=np.int32) * INR_DIM3D,
    np.ones(3, dtype=np.int32) * INR_DIM2D,
    np.ones(3, dtype=np.int32) * INR_DIM1D,
))
model = INR_FG_Evidential(feature_grid_shape, INR_SPATIAL_FDIM, INR_SPATIAL_FDIM,
                          INR_PARAM_FDIM, out_features=1, dropout_layer=False, gamma_sigmoid=False)
model.load_state_dict(torch.load(INR_WEIGHTS, map_location='cpu'))
model.eval().to(device)
# The inference service never trains the weights; /roi_optimize backprop only needs
# gradients w.r.t. the parameter inputs, so freezing the weights saves half the
# backward compute and GPU memory
for _p in model.parameters():
    _p.requires_grad_(False)


def build_coords(res=NYX_RES):
    """ 256^3 regular grid coordinates in [-1,1], meshgrid ij flattened (same per-voxel order as density.bin) """
    xs = np.linspace(-1, 1, res, dtype=np.float32)
    xv, yv, zv = np.meshgrid(xs, xs, xs, indexing='ij')
    return np.stack((xv.ravel(), yv.ravel(), zv.ravel()), axis=1).astype(np.float32)


# Coordinates stay resident on GPU (256^3x3 float32 ~= 200MB); each request only concatenates parameter columns and runs batched forwards
coords_gpu = torch.from_numpy(build_coords()).to(device)


def param_key(params):
    """ Deterministic filename prefix from parameters; same parameters -> same batch of vti files (file-level cache) """
    return "p" + "_".join(f"{float(p):.6g}" for p in params)


def run_inr_nig(params):
    """
    Run one INR forward over the full 256^3 field, returning flattened (gamma, v, alpha, beta),
    all float32, length 256^3, in the same order as build_coords / density.bin.
    """
    pn = normalize_param(np.array(params, dtype=np.float64), min_max_nyx_param).astype(np.float32)
    # The model is only valid within the training range, and DecompGrid uses the normalized
    # parameters as **integer indices** into 1D feature lines: values outside [0,1] cause
    # out-of-bounds indexing -> CUDA device-side assert, poisoning the whole CUDA context
    # (all subsequent requests fail). So hard-clamp to [0,1] here (equivalent to clamping
    # parameters to the boundary of the model's valid domain).
    pn = np.clip(pn, 0.0, 1.0)
    params_t = torch.from_numpy(pn).reshape(1, 3).to(device)

    n = coords_gpu.shape[0]
    gamma = np.empty(n, dtype=np.float32)
    v = np.empty(n, dtype=np.float32)
    alpha = np.empty(n, dtype=np.float32)
    beta = np.empty(n, dtype=np.float32)

    with torch.no_grad():
        for s in range(0, n, INR_BATCH):
            e = min(s + INR_BATCH, n)
            coord_batch = coords_gpu[s:e]
            param_batch = params_t.expand(e - s, 3)
            out = model(torch.cat((coord_batch, param_batch), dim=1))
            g, vv, aa, bb = torch.chunk(out, 4, dim=1)
            gamma[s:e] = g.squeeze(1).cpu().numpy()
            v[s:e] = vv.squeeze(1).cpu().numpy()
            alpha[s:e] = aa.squeeze(1).cpu().numpy()
            beta[s:e] = bb.squeeze(1).cpu().numpy()
    return gamma, v, alpha, beta


def get_nig(params):
    """ In-memory cache wrapper around run_inr_nig (most recent _NIG_CACHE_MAX parameter sets) """
    key = param_key(params)
    if key in _nig_cache:
        _nig_cache.move_to_end(key)
        return _nig_cache[key]
    val = run_inr_nig(params)
    _nig_cache[key] = val
    _nig_cache.move_to_end(key)
    while len(_nig_cache) > _NIG_CACHE_MAX:
        _nig_cache.popitem(last=False)
    return val


def convert_to_vti(dataname_dir, dataname, arrays_and_names):
    """
    Write a list of (array, filename without extension) directly to .vti in-process, returning the vti paths.
    Arrays are flattened in C order (same byte order/ordering as the old tofile+ConvertBinToVti.py).
    """
    vti_paths = []
    for data, file_name in arrays_and_names:
        vti_file_path = os.path.join(dataname_dir, f"{file_name}.vti")

        image_data = vtk.vtkImageData()
        image_data.SetDimensions(NYX_RES, NYX_RES, NYX_RES)
        image_data.SetSpacing(1.0, 1.0, 1.0)
        image_data.SetOrigin(0.0, 0.0, 0.0)

        flat = np.ascontiguousarray(data, dtype=np.float32).ravel()
        vtk_scalar_array = numpy_support.numpy_to_vtk(flat, deep=True, array_type=vtk.VTK_FLOAT)
        vtk_scalar_array.SetName('Scalar')
        image_data.GetPointData().SetScalars(vtk_scalar_array)

        writer = vtk.vtkXMLImageDataWriter()
        writer.SetFileName(vti_file_path)
        writer.SetInputData(image_data)
        # No compression + raw appended: zlib cannot compress these float fields (they even
        # get bigger), yet costs ~8s per file; raw writes take only ~0.1s, and vtk.js
        # XMLReader supports encoding="raw"
        writer.SetCompressorTypeToNone()
        writer.EncodeAppendedDataOff()
        if writer.Write() != 1:
            raise Exception(f"Failed to write {vti_file_path}")

        vti_paths.append(vti_file_path)
    return vti_paths


def generate_view1(dataname, params):
    """
    View1 triple: result(pred) / data_uncertainty(aleatoric std) / model_uncertainty(epistemic std).
    Returns immediately if the files already exist (cache hit).
    """
    dataname_dir = os.path.join(save_dir, dataname)
    os.makedirs(dataname_dir, exist_ok=True)

    key = param_key(params)
    names = [f"{key}_result", f"{key}_data_uncertainty", f"{key}_model_uncertainty"]
    vti_paths = [os.path.join(dataname_dir, f"{n}.vti") for n in names]
    if all(os.path.exists(p) for p in vti_paths):
        return vti_paths

    gamma, v, alpha, beta = get_nig(params)

    # pred is directly log10(rho): gamma * range + dmin (no baseline)
    pred = gamma * NYX_RANGE + NYX_DMIN
    # Uncertainty std (scaled back to the physical log10 scale)
    data_uncertainty = np.sqrt(beta / (alpha - 1.0) + 1e-9) * NYX_RANGE
    model_uncertainty = np.sqrt(beta / (v * (alpha - 1.0)) + 1e-9) * NYX_RANGE

    return convert_to_vti(dataname_dir, dataname, [
        (pred, names[0]),
        (data_uncertainty, names[1]),
        (model_uncertainty, names[2]),
    ])


def student_t_interval_norm(gamma, v, alpha, beta, confidence_level):
    """
    Student-t predictive interval (normalized space, no clipping).
    scale = sqrt(beta(1+v)/(v*alpha)), df = 2*alpha.
    Consistent with student_t_interval in Evidential_INR/fg_calibration_nyx_evidential.py:
    ensemble ground truth can exceed the [0,1] normalized range, and clipping would break the coverage guarantee.
    """
    st_scale = np.sqrt((beta * (1.0 + v)) / (v * alpha + 1e-9))
    st_df = 2.0 * alpha
    q = 1.0 - (1.0 - confidence_level) / 2.0

    # Interpolate t.ppf(q, df) on a log-df grid (computing it per-voxel directly is too slow)
    df_min, df_max = float(st_df.min()), float(st_df.max())
    if df_min == df_max:
        t_value = np.full_like(st_df, t.ppf(q, df_min))
    else:
        grid = np.logspace(np.log10(df_min * 0.999), np.log10(df_max * 1.001), 4096)
        t_value = np.interp(np.log(st_df), np.log(grid), t.ppf(q, grid)).astype(np.float32)

    lower = gamma - t_value * st_scale
    upper = gamma + t_value * st_scale
    return lower, upper


def generate_interval(dataname, params, confidence_level):
    """ View2 render: uncalibrated Student-t interval lower/upper bounds (physical log10 space). """
    dataname_dir = os.path.join(save_dir, dataname)
    os.makedirs(dataname_dir, exist_ok=True)

    key = f"{param_key(params)}_c{float(confidence_level):.4g}"
    names = [f"{key}_lower_bound", f"{key}_upper_bound"]
    vti_paths = [os.path.join(dataname_dir, f"{n}.vti") for n in names]
    if all(os.path.exists(p) for p in vti_paths):
        return vti_paths

    gamma, v, alpha, beta = get_nig(params)
    lower_n, upper_n = student_t_interval_norm(gamma, v, alpha, beta, confidence_level)
    lower = lower_n * NYX_RANGE + NYX_DMIN
    upper = upper_n * NYX_RANGE + NYX_DMIN

    return convert_to_vti(dataname_dir, dataname, [
        (lower, names[0]),
        (upper, names[1]),
    ])


def list_cal_levels():
    """ Scan Evidential_INR/outputs for calibration levels available for this model; returns [(level_value, calN, tag), ...]. """
    out = []
    pattern = os.path.join(cal_data_dir, f"{CAL_PREFIX}_cal*_Qlo_p*.bin")
    for f in glob.glob(pattern):
        base = os.path.basename(f)
        m = re.search(r"_(cal\d+)_Qlo_p([0-9_]+)\.bin$", base)
        if not m:
            continue
        cal_n, tag = m.group(1), m.group(2)
        try:
            val = float(tag.replace('_', '.'))
        except ValueError:
            continue
        out.append((val, cal_n, tag))
    return out


def pick_calibration_level(level):
    """ Pick the level closest to the requested confidence; ties prefer the larger calibration set (cal200>cal100, finer levels/more members). """
    avail = list_cal_levels()
    if not avail:
        return None
    return min(avail, key=lambda x: (abs(x[0] - level), -int(x[1][3:])))


@functools.lru_cache(maxsize=4)
def load_calibration(cal_n, tag):
    """ Load a level's per-voxel corrections Q_lo / Q_hi (each 256^3 float32, normalized space) """
    q_lo = np.fromfile(os.path.join(cal_data_dir, f"{CAL_PREFIX}_{cal_n}_Qlo_p{tag}.bin"), '<f4')
    q_hi = np.fromfile(os.path.join(cal_data_dir, f"{CAL_PREFIX}_{cal_n}_Qhi_p{tag}.bin"), '<f4')
    return q_lo, q_hi


def generate_calibrated_interval(dataname, params, confidence_level):
    """
    View2 calibration: conformally calibrated interval (paper Algorithm 1).
    C_{1-delta} = [q_lo - Q_lo, q_hi + Q_hi], no clipping in normalized space, then denormalized to physical log10.
    Uses the precomputed level closest to the requested confidence.
    """
    picked = pick_calibration_level(confidence_level)
    if picked is None:
        raise Exception(f"No calibration correction fields for {CAL_PREFIX} found under {cal_data_dir}")
    cal_val, cal_n, tag = picked

    dataname_dir = os.path.join(save_dir, dataname)
    os.makedirs(dataname_dir, exist_ok=True)

    # Filenames use the level actually adopted: requests for 0.7 / 0.72 hit the same cached files
    key = f"{param_key(params)}_c{cal_val:.4g}_calib"
    names = [f"{key}_lower_bound", f"{key}_upper_bound"]
    vti_paths = [os.path.join(dataname_dir, f"{n}.vti") for n in names]
    if all(os.path.exists(p) for p in vti_paths):
        return vti_paths, cal_val

    gamma, v, alpha, beta = get_nig(params)
    # Compute the raw interval at the confidence matching the calibration level
    lower_n, upper_n = student_t_interval_norm(gamma, v, alpha, beta, cal_val)

    q_lo, q_hi = load_calibration(cal_n, tag)
    lower_cal = lower_n - q_lo
    upper_cal = upper_n + q_hi

    lower = lower_cal * NYX_RANGE + NYX_DMIN
    upper = upper_cal * NYX_RANGE + NYX_DMIN

    vti_paths = convert_to_vti(dataname_dir, dataname, [
        (lower, names[0]),
        (upper, names[1]),
    ])
    return vti_paths, cal_val


@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json()
    params = data.get('param')
    dataname = data.get('dataname')
    datatype = data.get('datatype')
    confidence_level = data.get('confidence_level', 0.95)


    if params and len(params) == 1:
        # Old frontend versions sent the confidence as a parameter (param:[0.8]); new versions should send this row's 3 parameters
        return jsonify({'error': 'Frontend page is outdated; please close the tab and reopen it (or force refresh with Ctrl+Shift+R)',
                        'code': 1, 'message': 'stale frontend'}), 400
    if not params or len(params) != 3:
        return jsonify({'error': 'param array should contain exactly 3 elements (OmM, OmB, h).'}), 400

    try:
        if datatype == 1:
            vti_paths = generate_view1(dataname, params)
        elif datatype == 2:
            vti_paths = generate_interval(dataname, params, confidence_level)
        else:
            return jsonify({'error': 'Invalid Datatype value. Datatype should be 1 or 2.'}), 400
    except Exception as e:
        logging.error(f"generate failed: {e}")
        return jsonify({'data': [], 'code': 1, 'message': str(e)}), 500

    vti_filenames = [os.path.basename(path) for path in vti_paths]
    return jsonify({'data': vti_filenames, 'code': 0, 'message': 'success'})


@app.route('/calibration', methods=['POST'])
def calibration():
    data = request.get_json()
    params = data.get('param')
    dataname = data.get('dataname')
    confidence_level = data.get('confidence_level', 0.95)


    if not params or len(params) != 3:
        return jsonify({'error': 'param array should contain exactly 3 elements (OmM, OmB, h).'}), 400

    try:
        vti_paths, cal_level = generate_calibrated_interval(dataname, params, confidence_level)
    except Exception as e:
        logging.error(f"calibration failed: {e}")
        return jsonify({'data': [], 'code': 1, 'message': str(e)}), 500

    vti_filenames = [os.path.basename(path) for path in vti_paths]
    # calibration_level tells the frontend which calibration level was actually used (requested value snaps to the nearest existing level)
    return jsonify({'data': vti_filenames, 'code': 0, 'message': 'success',
                    'calibration_level': cal_level})


# ---------------------------------------------------------------------------
# View3: ROI parameter recommendation (activation maximization)
#   Treat the aggregated uncertainty inside the ROI as a differentiable objective of the
#   parameters, and run multi-start Adam gradient optimization directly on the normalized
#   parameters. The u = sigmoid(z) reparameterization guarantees values strictly in (0,1)
#   (going out of bounds blows up the CUDA context, see the run_inr_nig comment).
#   Fixed seed, so the same request is reproducible.
# ---------------------------------------------------------------------------
ROI_MAX_ROWS = 262144       # Max total points backpropagated per optimization step (across all starts)
ROI_EXACT_CHUNK = 1048576   # Chunk size for the final evaluation (gradient-free forward over the full ROI)
ROI_SEED = 20260710


def _roi_coords(roi):
    """ ROI voxel ranges [x0,x1,y0,y1,z0,z1] (inclusive) -> (N,3) [-1,1] coordinate tensor (GPU) """
    xs = np.linspace(-1, 1, NYX_RES, dtype=np.float32)
    ax = [xs[roi[0]:roi[1] + 1], xs[roi[2]:roi[3] + 1], xs[roi[4]:roi[5] + 1]]
    xv, yv, zv = np.meshgrid(*ax, indexing='ij')
    pts = np.stack((xv.ravel(), yv.ravel(), zv.ravel()), axis=1).astype(np.float32)
    return torch.from_numpy(pts).to(device)


def _roi_pointwise(out, objective, ref=None):
    """
    Model output (M,4) -> per-point objective values (physical log10 scale), keeping backprop intact.
    prediction: the predicted density itself; match: squared difference from the reference
    field (square-rooted after aggregation and reported as RMSE / max|diff|); the rest are
    uncertainty stds.
    """
    gamma, v, alpha, beta = torch.chunk(out, 4, dim=1)
    if objective == 'prediction':
        return gamma.squeeze(1) * NYX_RANGE + NYX_DMIN
    if objective == 'match':
        pred = gamma.squeeze(1) * NYX_RANGE + NYX_DMIN
        return (pred - ref) ** 2
    ale_var = beta / (alpha - 1.0 + 1e-9)
    epi_var = beta / (v * (alpha - 1.0) + 1e-9)
    var = {'aleatoric': ale_var, 'epistemic': epi_var,
           'predictive': ale_var + epi_var}[objective]
    return torch.sqrt(var + 1e-12).squeeze(1) * NYX_RANGE


def _roi_objective_batch(u, pts, objective, agg, ref=None):
    """ u: (S,3) normalized parameters, pts: (P,3) coordinates -> (S,) aggregated objective (one forward for all S starts) """
    s, p = u.shape[0], pts.shape[0]
    rows = torch.cat((pts.unsqueeze(0).expand(s, p, 3),
                      u.unsqueeze(1).expand(s, p, 3)), dim=2).reshape(s * p, 6)
    ref_rows = ref.unsqueeze(0).expand(s, p).reshape(s * p) if ref is not None else None
    val = _roi_pointwise(model(rows), objective, ref_rows).reshape(s, p)
    return val.amax(dim=1) if agg == 'max' else val.mean(dim=1)


def _roi_exact_values(u, roi_pts, objective, agg, ref=None):
    """ Exact gradient-free evaluation of each candidate over the full ROI -> (S,) numpy (used for final ranking) """
    vals = []
    with torch.no_grad():
        for i in range(u.shape[0]):
            acc = []
            for s in range(0, roi_pts.shape[0], ROI_EXACT_CHUNK):
                pts = roi_pts[s:s + ROI_EXACT_CHUNK]
                rows = torch.cat((pts, u[i].unsqueeze(0).expand(pts.shape[0], 3)), dim=1)
                ref_batch = ref[s:s + ROI_EXACT_CHUNK] if ref is not None else None
                acc.append(_roi_pointwise(model(rows), objective, ref_batch))
            val = torch.cat(acc)
            raw = float(val.max() if agg == 'max' else val.mean())
            # match's per-point value is the squared difference; square-root after aggregation -> RMSE (mean) / max|diff| (max)
            vals.append(float(np.sqrt(raw)) if objective == 'match' else raw)
    return np.array(vals)


# Reference field cache (flat float32 256^3, log10 space, same order as build_coords)
_ref_cache = OrderedDict()
_REF_CACHE_MAX = 3


def _load_ref_field(ref):
    """
    Reference field for the match objective (View3: user requests closeness to one of the
    middle panel's 5 predicted quantities):
      {'type':'field', 'kind': 'pred'|'lower'|'upper'|'lower_cal'|'upper_cal',
       'params': [OmM,OmB,h], 'confidence': c}
    kind corresponds, at the current context parameters, to the prediction / uncalibrated
    lower/upper bound / conformally calibrated lower/upper bound.
    Backward compatible with the old {'type':'mean'} / {'type':'member','id':N}.
    """
    rtype = (ref or {}).get('type')
    if rtype == 'mean':
        key = 'mean'
    elif rtype == 'member':
        key = f"member_{int(ref.get('id', -1))}"
    elif rtype == 'field':
        kind = ref.get('kind')
        if kind not in ('pred', 'lower', 'upper', 'lower_cal', 'upper_cal'):
            raise ValueError("ref.kind should be pred | lower | upper | lower_cal | upper_cal")
        params = ref.get('params')
        if not isinstance(params, (list, tuple)) or len(params) != 3:
            raise ValueError("ref.params should be [OmM, OmB, h] (the current context parameters)")
        conf = float(ref.get('confidence', 0.9))
        key = f"field_{kind}_{param_key(params)}_c{conf:.4g}"
    else:
        raise ValueError("ref.type should be field | mean | member")
    if key in _ref_cache:
        _ref_cache.move_to_end(key)
        return _ref_cache[key]

    if rtype == 'mean':
        field = np.fromfile(os.path.join(ensemble_stats_dir, 'voxelwise', 'mean.bin'), '<f4')
    elif rtype == 'member':
        m = ensemble_members().get(int(ref['id']))
        if m is None:
            raise ValueError(f"member {ref['id']} does not exist (available: 0..{len(ensemble_members()) - 1})")
        raw = os.path.join(ensemble_raw_root, m['dir'], 'Raw_plt256_00200', 'density.bin')
        field = np.log10(np.maximum(np.fromfile(raw, '<f4').astype(np.float64), 1e-30)).astype(np.float32)
    else:
        # Same math as generate_view1 / generate_interval / generate_calibrated_interval,
        # flattened in the same order as build_coords (the NIG forward has an in-memory cache, usually a direct hit)
        gamma, v, alpha, beta = get_nig([float(p) for p in params])
        if kind == 'pred':
            field = gamma * NYX_RANGE + NYX_DMIN
        elif kind in ('lower', 'upper'):
            lo, hi = student_t_interval_norm(gamma, v, alpha, beta, conf)
            field = (lo if kind == 'lower' else hi) * NYX_RANGE + NYX_DMIN
        else:
            picked = pick_calibration_level(conf)
            if picked is None:
                raise ValueError(f"No calibration correction fields found under {cal_data_dir}")
            cal_val, cal_n, tag = picked
            lo, hi = student_t_interval_norm(gamma, v, alpha, beta, cal_val)
            q_lo, q_hi = load_calibration(cal_n, tag)
            field = ((lo - q_lo) if kind == 'lower_cal' else (hi + q_hi)) * NYX_RANGE + NYX_DMIN
        field = np.ascontiguousarray(field, dtype=np.float32)
    if field.size != NYX_RES ** 3:
        raise ValueError(f"Unexpected reference field size: {field.size}")

    _ref_cache[key] = field
    while len(_ref_cache) > _REF_CACHE_MAX:
        _ref_cache.popitem(last=False)
    return field


@app.route('/roi_optimize', methods=['POST'])
def roi_optimize():
    data = request.get_json()
    roi = data.get('roi')
    objective = data.get('objective', 'aleatoric')
    agg = data.get('agg', 'mean')
    direction = data.get('direction', 'max')
    n_starts = max(1, min(int(data.get('n_starts', 8)), 32))
    n_steps = max(10, min(int(data.get('n_steps', 150)), 500))
    top_k = max(1, min(int(data.get('top_k', 3)), 32))
    eval_params = data.get('eval_params')

    if not isinstance(roi, (list, tuple)) or len(roi) != 6:
        return jsonify({'error': 'roi should be six voxel indices [x0,x1,y0,y1,z0,z1]'}), 400
    roi = [int(x) for x in roi]
    for lo, hi in ((roi[0], roi[1]), (roi[2], roi[3]), (roi[4], roi[5])):
        if not (0 <= lo <= hi <= NYX_RES - 1):
            return jsonify({'error': f'roi out of bounds: each dimension must satisfy 0 <= lo <= hi <= {NYX_RES - 1}'}), 400
    if objective not in ('aleatoric', 'epistemic', 'predictive', 'prediction', 'match'):
        return jsonify({'error': 'objective should be aleatoric | epistemic | predictive | prediction | match'}), 400
    if agg not in ('mean', 'max'):
        return jsonify({'error': 'agg should be mean | max'}), 400
    if direction not in ('min', 'max'):
        return jsonify({'error': 'direction should be min | max'}), 400

    roi_pts = _roi_coords(roi)
    n_roi = roi_pts.shape[0]
    p = min(n_roi, max(1, ROI_MAX_ROWS // n_starts))

    # match objective: take the ROI portion of the reference field (same slicing and flattening order as _roi_coords)
    ref_roi = None
    if objective == 'match':
        try:
            field = _load_ref_field(data.get('ref'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        ref_roi = torch.from_numpy(np.ascontiguousarray(
            field.reshape(NYX_RES, NYX_RES, NYX_RES)[roi[0]:roi[1] + 1, roi[2]:roi[3] + 1, roi[4]:roi[5] + 1].ravel()
        )).to(device)

    # Multi-start: the 1st start is at the center of parameter space, the rest are random with a fixed seed (reproducible results)
    gen = torch.Generator().manual_seed(ROI_SEED)
    u0 = torch.rand(n_starts, 3, generator=gen) * 0.9 + 0.05
    u0[0] = 0.5
    z = torch.logit(u0).to(device).requires_grad_(True)
    opt = torch.optim.Adam([z], lr=0.05)
    sign = -1.0 if direction == 'max' else 1.0   # Adam only minimizes

    gen_gpu = torch.Generator(device=device.type).manual_seed(ROI_SEED)
    for _ in range(n_steps):
        if p < n_roi:   # If the ROI is too large, randomly subsample each step (SGD); the final evaluation still uses the full ROI
            idx = torch.randint(0, n_roi, (p,), generator=gen_gpu, device=device)
            pts = roi_pts[idx]
            ref_batch = ref_roi[idx] if ref_roi is not None else None
        else:
            pts = roi_pts
            ref_batch = ref_roi
        obj = _roi_objective_batch(torch.sigmoid(z), pts, objective, agg, ref_batch)
        loss = (sign * obj).sum()
        opt.zero_grad()
        loss.backward()
        opt.step()

    with torch.no_grad():
        u = torch.sigmoid(z)
        # sigmoid never reaches 0/1, yet the features are piecewise-linear in the parameters and the optimum is often on the boundary: snap near-boundary solutions to the boundary
        u = torch.where(u > 0.995, torch.ones_like(u), u)
        u = torch.where(u < 0.005, torch.zeros_like(u), u)
    vals = _roi_exact_values(u, roi_pts, objective, agg, ref_roi)

    order = np.argsort(-vals) if direction == 'max' else np.argsort(vals)
    mm = np.array(min_max_nyx_param)
    picked = []
    for i in order:
        ui = u[i].cpu().numpy()
        if any(np.abs(ui - q['_un']).max() < 0.02 for q in picked):
            continue    # Multiple starts converged to the same solution, deduplicate
        real = mm[:, 0] + (mm[:, 1] - mm[:, 0]) * ui
        picked.append({'_un': ui,
                       'params': [float(f'{x:.6g}') for x in real],
                       'params_norm': [round(float(x), 4) for x in ui],
                       'value': float(vals[i])})
        if len(picked) >= top_k:
            break
    # match objective: add ROI-mean aleatoric / epistemic to each candidate; the frontend
    # re-ranks candidates by "closest to reference + user preference for high/low uncertainty"
    if objective == 'match':
        for q in picked:
            uu = torch.from_numpy(q['_un'].astype(np.float32)).reshape(1, 3).to(device)
            q['aleatoric'] = float(_roi_exact_values(uu, roi_pts, 'aleatoric', agg)[0])
            q['epistemic'] = float(_roi_exact_values(uu, roi_pts, 'epistemic', agg)[0])
    for q in picked:
        q.pop('_un')

    resp = {'code': 0, 'message': 'success', 'roi': roi, 'n_voxels': int(n_roi),
            'objective': objective, 'agg': agg, 'direction': direction,
            'recommendations': picked}
    if objective == 'match':
        resp['ref'] = data.get('ref')

    # Optional: evaluate given parameters (e.g. the user's current ones) under the same objective, for frontend comparison
    if eval_params:
        ev = []
        for pr in eval_params:
            if not isinstance(pr, (list, tuple)) or len(pr) != 3:
                return jsonify({'error': 'each entry of eval_params should be [OmM, OmB, h]'}), 400
            pn = np.clip(normalize_param(np.array(pr, dtype=np.float64), min_max_nyx_param), 0.0, 1.0)
            uu = torch.from_numpy(pn.astype(np.float32)).reshape(1, 3).to(device)
            entry = {'params': [float(x) for x in pr],
                     'value': float(_roi_exact_values(uu, roi_pts, objective, agg, ref_roi)[0])}
            if objective == 'match':
                entry['aleatoric'] = float(_roi_exact_values(uu, roi_pts, 'aleatoric', agg)[0])
                entry['epistemic'] = float(_roi_exact_values(uu, roi_pts, 'epistemic', agg)[0])
            ev.append(entry)
        resp['eval'] = ev

    return jsonify(resp)


# ---------------------------------------------------------------------------
# View3: parameter sensitivity analysis (differentiable NN version)
#   For each parameter, sweep n points across its range (the other two parameters fixed
#   at the current context values); each point's forward yields the spatial mean/std of
#   the predicted log10 density inside the ROI, and autograd gives the exact derivative
#   d(ROI mean)/d(parameter) -- structurally the same as Module 1's ensemble line chart,
#   but the curves come from the surrogate model's (Evidential INR) analytic
#   differentiability rather than a finite set of simulation members.
# ---------------------------------------------------------------------------
SENS_MAX_PTS = 32768   # ROI subsampling cap: all sweep points share the same batch of spatial points, so curves are smooth and comparable


@app.route('/param_sensitivity', methods=['POST'])
def param_sensitivity():
    data = request.get_json()
    roi = data.get('roi')
    params = data.get('params')
    n_points = max(5, min(int(data.get('n_points', 21)), 81))

    if not isinstance(roi, (list, tuple)) or len(roi) != 6:
        return jsonify({'error': 'roi should be six voxel indices [x0,x1,y0,y1,z0,z1]'}), 400
    roi = [int(x) for x in roi]
    for lo, hi in ((roi[0], roi[1]), (roi[2], roi[3]), (roi[4], roi[5])):
        if not (0 <= lo <= hi <= NYX_RES - 1):
            return jsonify({'error': f'roi out of bounds: each dimension must satisfy 0 <= lo <= hi <= {NYX_RES - 1}'}), 400
    if not isinstance(params, (list, tuple)) or len(params) != 3:
        return jsonify({'error': 'params should be [OmM, OmB, h]'}), 400

    roi_pts = _roi_coords(roi)
    n_roi = roi_pts.shape[0]
    if n_roi > SENS_MAX_PTS:   # Fixed-seed subsampling, so repeated requests for the same ROI give identical results
        g = torch.Generator(device=device.type).manual_seed(ROI_SEED)
        idx = torch.randperm(n_roi, generator=g, device=device)[:SENS_MAX_PTS]
        roi_pts = roi_pts[idx]

    pn = np.clip(normalize_param(np.array(params, dtype=np.float64), min_max_nyx_param), 0.0, 1.0)
    base = torch.tensor(pn, dtype=torch.float32, device=device)
    mm = np.array(min_max_nyx_param, dtype=np.float64)
    names = ['OmM', 'OmB', 'h']

    curves, sens = [], []
    for d in range(3):
        span = float(mm[d, 1] - mm[d, 0])
        pts_curve, grads = [], []
        for xv in np.linspace(0.0, 1.0, n_points):
            u = base.clone()
            u[d] = float(xv)
            u = u.reshape(1, 3).requires_grad_(True)
            rows = torch.cat((roi_pts, u.expand(roi_pts.shape[0], 3)), dim=1)
            gamma = torch.chunk(model(rows), 4, dim=1)[0].squeeze(1)
            pred = gamma * NYX_RANGE + NYX_DMIN
            m, s = pred.mean(), pred.std()
            g_norm = float(torch.autograd.grad(m, u)[0][0, d])  # d mean / d u_d (normalized parameter)
            grads.append(g_norm)
            pts_curve.append({'x': float(mm[d, 0] + span * xv),
                              'mean': float(m), 'std': float(s),
                              'grad': g_norm / span})            # derivative in physical units
        curves.append({'param': names[d], 'min': float(mm[d, 0]), 'max': float(mm[d, 1]),
                       'current': float(params[d]), 'points': pts_curve})
        # Sensitivity metric: mean of |d mean / d u| over the full sweep (normalized parameter, comparable across parameters)
        sens.append(float(np.mean(np.abs(grads))))

    return jsonify({'code': 0, 'message': 'success', 'roi': roi,
                    'n_sample_pts': int(roi_pts.shape[0]), 'n_roi': int(n_roi),
                    'sensitivity': sens, 'curves': curves})


# ---------------------------------------------------------------------------
# Dataset Exploration module: volume rendering of ensemble members / voxelwise statistic fields
# ---------------------------------------------------------------------------
ensemble_stats_dir = os.path.join(PROJECT_ROOT, "ensemble_stats_430")
# Raw simulation members are only needed by raw-volume/detail endpoints, not by
# surrogate inference or the precomputed ensemble-statistics views.
ensemble_raw_root = os.environ.get(
    "NYX_DATA_ROOT", os.path.join(PROJECT_ROOT, "data", "nyx", "256", "output")
)
ensemble_public_dir = os.path.join(save_dir, "ensemble")  # separate from the nyx directory managed by /clean

_ensemble_members = None


def ensemble_members():
    global _ensemble_members
    if _ensemble_members is None:
        import json as _json
        with open(os.path.join(ensemble_stats_dir, "members.json")) as f:
            _ensemble_members = {m['id']: m for m in _json.load(f)}
    return _ensemble_members


@app.route('/ensemble/member/<int:member_id>', methods=['POST'])
def ensemble_member(member_id):
    """ Generate the log10 density field vti by member id (file-level cache); returns a filename usable directly with setUrl """
    try:
        m = ensemble_members().get(member_id)
        if m is None:
            return jsonify({'data': None, 'code': 1, 'message': f'member {member_id} does not exist'}), 404

        os.makedirs(ensemble_public_dir, exist_ok=True)
        name = f"member_{member_id:04d}_log10"
        vti_path = os.path.join(ensemble_public_dir, f"{name}.vti")
        if not os.path.exists(vti_path):
            raw = os.path.join(ensemble_raw_root, m['dir'], "Raw_plt256_00200", "density.bin")
            data = np.fromfile(raw, '<f4').astype(np.float64)
            data = np.log10(np.maximum(data, 1e-30)).astype('<f4').reshape(256, 256, 256)
            convert_to_vti(ensemble_public_dir, 'nyx', [(data, name)])

        return jsonify({'data': {'vti': f"/ensemble/{name}.vti", 'member': m},
                        'code': 0, 'message': 'success'})
    except Exception as e:
        logging.error(f"ensemble_member failed: {e}")
        return jsonify({'data': None, 'code': 1, 'message': str(e)}), 500


@app.route('/ensemble/voxelwise/<stat>', methods=['POST'])
def ensemble_voxelwise(stat):
    """ Convert a voxelwise statistic field (mean/std/w90/... 16 total) to vti (cached), for the overview view """
    try:
        src = os.path.join(ensemble_stats_dir, "voxelwise", f"{stat}.bin")
        if not re.fullmatch(r"[a-z0-9]+", stat) or not os.path.exists(src):
            return jsonify({'data': None, 'code': 1, 'message': f'unknown statistic field {stat}'}), 404

        os.makedirs(ensemble_public_dir, exist_ok=True)
        name = f"voxelwise_{stat}"
        vti_path = os.path.join(ensemble_public_dir, f"{name}.vti")
        if not os.path.exists(vti_path):
            data = np.fromfile(src, '<f4').reshape(256, 256, 256)
            convert_to_vti(ensemble_public_dir, 'nyx', [(data, name)])

        return jsonify({'data': {'vti': f"/ensemble/{name}.vti"}, 'code': 0, 'message': 'success'})
    except Exception as e:
        logging.error(f"ensemble_voxelwise failed: {e}")
        return jsonify({'data': None, 'code': 1, 'message': str(e)}), 500


@app.route('/ai/status', methods=['GET'])
def ai_status():
    """ AI assistant status: provider / model / knowledge-base document count (probed by the frontend at startup) """
    import ai_agent
    try:
        return jsonify({'data': ai_agent.status(), 'code': 0, 'message': 'success'})
    except Exception as e:
        logging.error(f"ai_status failed: {e}")
        return jsonify({'data': None, 'code': 1, 'message': str(e)}), 500


@app.route('/ai/chat', methods=['POST'])
def ai_chat():
    """ AI assistant chat: RAG (DatabasePDF knowledge base) + current application state """
    import ai_agent
    body = request.get_json()
    messages = body.get('messages') or []
    app_state = body.get('app_state')
    if not messages:
        return jsonify({'data': None, 'code': 1, 'message': 'messages must not be empty'}), 400
    try:
        result = ai_agent.chat(messages, app_state)
        return jsonify({'data': result, 'code': 0, 'message': 'success'})
    except Exception as e:
        logging.error(f"ai_chat failed: {e}")
        return jsonify({'data': None, 'code': 1, 'message': str(e)}), 500


@app.route('/clean', methods=['POST'])
def clean():
    """ One-click cleanup: delete all generated .vti/.bin files """
    removed = 0
    try:
        # Per-dataset subdirectories under frontend public (nyx / mpas / cloverleaf)
        for name in ('nyx', 'mpas', 'cloverleaf'):
            d = os.path.join(save_dir, name)
            if os.path.isdir(d):
                for f in os.listdir(d):
                    os.remove(os.path.join(d, f))
                    removed += 1
    except Exception as e:
        logging.error(f"clean failed: {e}")
        return jsonify({'data': None, 'code': 1, 'message': str(e)}), 500

    return jsonify({'data': {'removed': removed}, 'code': 0, 'message': 'success'})


if __name__ == '__main__':
    # macOS's AirPlay receiver occupies port 5000, so use 5001 here (the frontend vite proxy is already in sync)
    # When frontend and backend are on different nodes, set BIND_HOST=0.0.0.0; in that case
    # disable debug to avoid exposing the Werkzeug debugger to the whole cluster
    bind_host = os.environ.get('BIND_HOST', '127.0.0.1')
    app.run(host=bind_host, port=5001, debug=(bind_host == '127.0.0.1'))
