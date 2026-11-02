"""Inspect the actual closed winding, independently of saved layer decisions."""
import numpy as np
from scipy.spatial import cKDTree
from .wire_geometry import closed_wire_path


def cylindrical_layer_distribution(path, design_radius, shift_length, diameter):
    """Require at most one return branch at each projected crossing.

    The 10% layer bands tolerate mesh faceting and averaged normals. A transition
    belongs to the return branch: it may cross the original layer, but two return
    branches must not cross each other at different intermediate radii. This
    sampled-projection criterion complements,
    never replaces, real-conductor 3D clearance and curvature measurements.
    """
    p = closed_wire_path(path)
    radii = np.linalg.norm(p[:, :2], axis=1)
    lengths = np.linalg.norm(np.diff(p, axis=0), axis=1)
    positions = np.r_[0., np.cumsum(lengths)]
    found = {}
    cross = lambda a,b: a[:,0]*b[:,1]-a[:,1]*b[:,0]
    for offset in (0., 2*np.pi/3, 4*np.pi/3):
        angle = (np.arctan2(p[:,1],p[:,0])+offset+np.pi)%(2*np.pi)-np.pi
        uv = np.c_[angle*design_radius,p[:,2]]
        ids = np.flatnonzero(np.abs(np.diff(angle))<np.pi)
        if not len(ids):
            continue
        a, vectors = uv[ids], uv[ids+1]-uv[ids]
        half = np.linalg.norm(vectors,axis=1)/2
        neighbors = cKDTree(a+vectors/2).query_ball_point(a+vectors/2,half+half.max()+1e-12)
        left = np.repeat(np.arange(len(ids)),[len(group) for group in neighbors])
        right = np.concatenate(neighbors)
        keep = right>left+1
        left,right = left[keep],right[keep]
        u,v,delta = vectors[left],vectors[right],a[right]-a[left]
        den = cross(u,v)
        keep = np.abs(den)>1e-18
        left,right,u,v,delta,den = [value[keep] for value in (left,right,u,v,delta,den)]
        t,s = cross(delta,v)/den,cross(delta,u)/den
        keep = (t>1e-9)&(t<1-1e-9)&(s>1e-9)&(s<1-1e-9)
        for i,j,ta,tb in zip(ids[left[keep]],ids[right[keep]],t[keep],s[keep]):
            arc = min(positions[j]-positions[i+1],positions[-1]-positions[j+1]+positions[i])
            if arc<=2*diameter:
                continue
            found[(int(i),int(j))] = ((1-ta)*radii[i]+ta*radii[i+1],(1-tb)*radii[j]+tb*radii[j+1])
    depth = abs(shift_length)
    lower,upper = sorted((design_radius,design_radius+shift_length))
    def classify(radius):
        if depth == 0:
            return 'outer'
        return 'inner' if radius<lower+.1*depth else ('outer' if radius>upper-.1*depth else 'transition')
    counts = {'inner+inner':0,'outer+outer':0,'inner+outer':0}
    # Inward returns: outer+transition is one bridge under the original layer.
    # Outward returns use the symmetric rule. Physical clearance is independent.
    allowed = {'inner+outer', 'outer+transition' if shift_length<0 else 'inner+transition'}
    violations = []
    for pair, pair_radii in sorted(found.items()):
        classes = sorted(classify(radius) for radius in pair_radii)
        key = '+'.join(classes)
        counts[key] = counts.get(key,0)+1
        if key not in allowed:
            violations.append(dict(segments=list(pair),layers=classes,
                                   radii_mm=[float(radius*1000) for radius in pair_radii]))
    return dict(status='satisfied' if not violations else 'unresolved', criterion='no_crossings_between_return_branches',
        crossing_count=len(found), classes=counts, unresolved_crossing_count=len(violations),
        violations=violations, layer_band_fraction=.1, nominal_radii_mm=[lower*1000,upper*1000],
        local_arc_exclusion_mm=2*diameter*1000,closed_loop=True,
        scope='proper_intersections_of_sampled_cylindrical_projection; endpoints_and_collinear_touches_excluded')


def solution_return_path_distribution(parts, args):
    """Recheck after all repairs, on the selected route and current orientation."""
    from pyCoilGen.sub_functions.calc_3d_rotation_matrix_by_vector import calc_3d_rotation_matrix_by_vector
    parameters = getattr(args,'cylinder_mesh_parameter_list',[])
    if not getattr(args,'surface_is_cylinder_flag',False) or len(parameters)!=8:
        return dict(status='not_checked',reason='requires_generated_cylinder',parts=[])
    rotation = calc_3d_rotation_matrix_by_vector(np.asarray(parameters[4:7]),parameters[7])
    reports = []
    for part in parts:
        report = cylindrical_layer_distribution(part.wire_path.v.T@rotation.T,float(parameters[1]),
            float(args.normal_shift_length),float(args.conductor_thickness))
        if hasattr(part,'return_path_report'):
            part.return_path_report['final_distribution'] = report
        reports.append(report)
    return dict(status='satisfied' if all(report['status']=='satisfied' for report in reports) else 'unresolved',
        parts=reports, unresolved_crossing_count=sum(report['unresolved_crossing_count'] for report in reports))


def return_path_distribution_message(report,language='es'):
    count = report.get('unresolved_crossing_count',0)
    if language=='en':
        return (f'The winding does not meet the requested return-path distribution: {count} projected '
                'crossing(s) remain between return branches or within the original layer. This is separate from round-wire '
                'clearance. Review the return-path layer plan and connections; leads and mold were not generated.')
    return (f'El bobinado no cumple la distribución de retornos: quedan {count} cruce(s) proyectado(s) '
            'entre ramas de retorno o dentro de la capa original. Es un criterio distinto de la separación del cable '
            'circular. Revise el reparto de capas y las conexiones; no se generaron terminales ni molde.')
