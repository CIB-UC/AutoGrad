"""Versioned, non-pickle return-path evidence and exact replay without a solve.

The archived input is specific to its mesh, station ordering and effective
parameters. Replaying it is not a way to transfer a layer plan to another coil.
"""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile

import numpy as np


def _json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def _sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _atomic_write(path, writer):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer(stream)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def save_return_path_traces(parts, args, *, stage):
    """Persist the selected route, including a failed joint decision, at a stage.

    Called before sweeping and again after recovery/current orientation. No
    iteration limits, layer choices, or manufacturing checks are changed here.
    """
    if not getattr(args, 'save_return_path_trace', False):
        return
    root = Path(__file__).resolve().parents[2]
    modules = [*root.joinpath('pyCoilGen').rglob('*.py'), *root.joinpath('halbach_coils').rglob('*.py')]
    sources = {str(path.relative_to(root)).replace('\\', '/'): _sha256(path) for path in sorted(modules)}
    output = Path(args.output_directory)
    output.mkdir(parents=True, exist_ok=True)
    for index, part in enumerate(parts):
        trace = getattr(part, 'return_path_trace', None)
        if trace is None:
            continue
        if stage == 'final':
            trace['final_v'] = part.wire_path.v.copy()
            trace['final_uv'] = part.wire_path.uv.copy()
        path = output/f'{args.project_name}_wire_{index}_return_paths.npz'
        _atomic_write(path, lambda stream: np.savez_compressed(stream, **trace))
        metadata = dict(schema_version=1, coordinate_frame='physical_xyz', units='m', stage=stage,
            trace_sha256=_sha256(path), layer_plan=part.return_path_report,
            clearance=getattr(part, 'clearance_report', None),
            effective_args=getattr(part, 'return_path_effective_args', vars(args)),
            requested_args=vars(args), source_sha256=sources,
            python_version=sys.version, numpy_version=np.__version__,
            scope='Sampled winding stages, including closed-loop recovery. No winding feasibility certification.')
        content = (json.dumps(metadata, default=_json_value, indent=2, allow_nan=False)+'\n').encode('utf-8')
        _atomic_write(path.with_suffix('.json'), lambda stream: stream.write(content))
        part.return_path_report['trace_file'] = path.name
        part.return_path_report['trace_metadata_file'] = path.with_suffix('.json').name


def replay_return_path_trace(filename, *, stage='shifted', verify_planner=True):
    """Recompute displacement exactly, or retrieve an explicitly recorded stage.

    Always verify the archive hash. By default also recompute the current
    deterministic planner and reject changed layer decisions. A recorded later
    recovery is retrieved, never silently repeated under wall-clock limits.
    Returns N x 3 physical XYZ metres, without changing the source archive.
    """
    from .shift_return_paths import LAYER_PLANNER_VERSIONS, plan_return_path_layers
    path = Path(filename)
    metadata = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    if (metadata.get('schema_version') != 1 or metadata.get('coordinate_frame') != 'physical_xyz'
            or metadata.get('units') != 'm' or _sha256(path) != metadata.get('trace_sha256')):
        raise ValueError('Unsupported or changed return-path archive')
    with np.load(path, allow_pickle=False) as data:
        if verify_planner:
            if metadata['layer_plan']['algorithm'] not in LAYER_PLANNER_VERSIONS:
                raise ValueError('Return-path planner version differs from the recorded plan')
            args = metadata['effective_args']
            plan = plan_return_path_layers(data['surface_uv'], data['crossing_segments'],
                args['normal_shift_smooth_factors'], args['normal_shift_length'],
                args.get('conductor_thickness', 0.), reassign=args.get('reassign_crossing_layers', True),
                version=metadata['layer_plan']['algorithm'])
            for archived, computed in [('historical_points','historical_points'),
                                       ('historical_shift','historical_shift'),
                                       ('selected_points','points'), ('selected_shift','shift'),
                                       ('selected_factors','factors'), ('kernel','kernel')]:
                if not np.array_equal(data[archived], plan[computed]):
                    raise ValueError(f'Planner no longer reproduces {archived}')
        # Keep the historical multiplication/addition order, including averaged normals.
        reproduced = data['surface_v']+data['effective_normals']*data['selected_shift'][None, :]*metadata['effective_args']['normal_shift_length']
        if not np.array_equal(reproduced, data['shifted_v']):
            raise ValueError('Recorded displacement does not reproduce the shifted path')
        if stage not in ('shifted', 'pruned', 'recovered', 'final') or stage+'_v' not in data:
            raise ValueError(f'Stage {stage!r} is not recorded in this archive')
        return (reproduced if stage == 'shifted' else data[stage+'_v']).T.copy()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--stage', choices=('shifted','pruned','recovered','final'), default='shifted')
    parser.add_argument('--output', required=True, help='New diagnostic NPZ; existing files are preserved')
    options = parser.parse_args()
    path = replay_return_path_trace(options.archive, stage=options.stage)
    # Exclusive create: replay cannot accidentally replace an original result.
    with Path(options.output).open('xb') as stream:
        np.savez_compressed(stream, path=path, units=np.asarray('m'), coordinate_frame=np.asarray('physical_xyz'))
    print(f'Replayed {len(path)} stations at {options.stage}; planner and archive verified.')


if __name__ == '__main__':
    main()
