"""Remove only fixed context-road depiction outside the modeled ground.

All recipes and guards are planar and leave their immutable inputs untouched.
The caller builds the two meshes and supplies their actual world faces back to
verify_context_meshes; this module does not load, save or render a scene.
"""
import hashlib


def _parts(shape):
    if shape.is_empty:
        return []
    if shape.geom_type == 'Polygon':
        return [shape]
    return [part for child in getattr(shape, 'geoms', ()) for part in _parts(child)]


def _sha(shape):
    from shapely import normalize, to_wkb
    return hashlib.sha256(to_wkb(normalize(shape), byte_order=1,
                                 output_dimension=2)).hexdigest()


def clean_context_roads(road, curbs, *, ground, source_roads, protected_roads, gates):
    from shapely.geometry import LineString, Point, box
    from shapely.ops import nearest_points, unary_union

    tolerance = 1e-7
    names = ['钱荣路', '外部道路南段']
    assert sorted(row['name'] for row in source_roads) == sorted(names)
    assert len(gates) == 3 and {row['id'] for row in gates} == {'gate1', 'gate2', 'gate3'}
    assert all(shape.is_valid and not shape.is_empty for shape in (road, curbs, ground))
    original = [_sha(shape) for shape in (road, curbs, ground)]
    assert protected_roads and not ({row['name'] for row in protected_roads} & set(names))
    source_records = []; connector_records = []; source_shapes = {}; connectors = []
    for row in sorted([*source_roads, *protected_roads], key=lambda value: value['name']):
        # Reuse the exact earlier traced polygon, and independently check the
        # same gp coordinates / width / default round caps and round joins.
        expected = LineString(row['points_world']).buffer(row['width_m'] / 2,
                                                         join_style='round')
        assert row['footprint'].equals(expected), row['name']
        record = {'name': row['name'], 'width_m': row['width_m'],
            'points_world': [list(point) for point in row['points_world']],
            'buffer_join_style': 'round', 'buffer_cap_style': 'round',
            'buffer_quad_segs': 16, 'source_geometry_sha256': _sha(expected)}
        if row['name'] in names:
            source_shapes[row['name']] = row['footprint']; source_records.append(record)
        else:
            connectors.append(row['footprint']); connector_records.append(record)
    connector_union = unary_union(connectors)
    context_outside_ground = unary_union(list(source_shapes.values())).difference(ground)
    connector_overlap = road.intersection(context_outside_ground).intersection(connector_union)
    allowed_road = context_outside_ground.difference(connector_union)
    # Buffer only for removing the old curb around a removed external road.
    # Subtract ground again so the buffer cannot erode a retained campus curb.
    connector_curb_protection = connector_union.buffer(.25)
    allowed_curb = allowed_road.buffer(.25).difference(ground).difference(connector_curb_protection)
    new_road = road.difference(allowed_road)
    new_curbs = curbs.difference(allowed_curb)
    assert new_road.is_valid and new_curbs.is_valid
    removed_road = road.difference(new_road)
    removed_curbs = curbs.difference(new_curbs)
    assert removed_road.area > 1.0 and removed_curbs.area > 0
    connector_road_loss = removed_road.intersection(connector_union).area
    connector_curb_loss = removed_curbs.intersection(connector_curb_protection).area
    assert connector_road_loss < tolerance and connector_curb_loss < tolerance

    def metrics(before, after, allowed):
        inside_before = before.intersection(ground)
        inside_after = after.intersection(ground)
        outside_new = after.difference(before).area
        inside_difference = inside_before.symmetric_difference(inside_after).area
        difference_outside_mask = before.symmetric_difference(after).difference(allowed).area
        assert outside_new < tolerance
        assert inside_difference < tolerance
        assert difference_outside_mask < tolerance
        return {'before_area_m2': before.area, 'after_area_m2': after.area,
            'removed_area_m2': before.difference(after).area,
            'inside_ground_difference_m2': inside_difference,
            'outside_allowed_mask_difference_m2': difference_outside_mask,
            'new_outside_old_area_m2': outside_new,
            'components_before': len(_parts(before)), 'components_after': len(_parts(after)),
            'allowed_removal_mask_area_m2': allowed.area,
            'allowed_removal_mask_inside_ground_m2': allowed.intersection(ground).area,
            'allowed_removal_mask_sha256': _sha(allowed)}
    road_checks = metrics(road, new_road, allowed_road)
    curb_checks = metrics(curbs, new_curbs, allowed_curb)
    assert road_checks['allowed_removal_mask_inside_ground_m2'] < tolerance
    assert curb_checks['allowed_removal_mask_inside_ground_m2'] < tolerance

    # Deleting an exterior bridge may legitimately change total road parts.
    # The campus-only road geometry and every one of its parts/holes may not.
    inside_before = road.intersection(ground)
    inside_after = new_road.intersection(ground)
    inside_parts_before = _parts(inside_before); inside_parts_after = _parts(inside_after)
    assert len(inside_parts_before) == len(inside_parts_after)
    for part in inside_parts_before:
        retained = _parts(inside_after.intersection(part))
        assert len(retained) == 1 and len(retained[0].interiors) == len(part.interiors)
        assert part.symmetric_difference(retained[0]).area < tolerance
    old_contact = road.intersection(ground.boundary)
    new_contact = new_road.intersection(ground.boundary)
    contact_lost = old_contact.difference(new_contact).length
    contact_added = new_contact.difference(old_contact).length
    assert contact_lost < tolerance and contact_added < tolerance
    connectivity = {'inside_component_count_before': len(inside_parts_before),
        'inside_component_count_after': len(inside_parts_after),
        'inside_hole_count_before': sum(len(part.interiors) for part in inside_parts_before),
        'inside_hole_count_after': sum(len(part.interiors) for part in inside_parts_after),
        'each_inside_component_and_its_holes_preserved': True,
        'ground_boundary_contact_length_before_m': old_contact.length,
        'ground_boundary_contact_length_after_m': new_contact.length,
        'ground_boundary_contact_lost_length_m': contact_lost,
        'ground_boundary_contact_added_length_m': contact_added}
    assert connectivity['inside_hole_count_before'] == connectivity['inside_hole_count_after']

    gate_checks = []
    for row in sorted(gates, key=lambda value: value['id']):
        point = Point(row['world_xy']); nearby = point.buffer(12)
        road_changed = removed_road.intersection(nearby).area
        curb_changed = removed_curbs.intersection(nearby).area
        # Any true gate affected by this scoped patch requires a source-led
        # design decision; never silently invent an exterior connector here.
        assert road_changed < tolerance and curb_changed < tolerance, row['id']
        gate_checks.append({'id': row['id'], 'source': row['source'],
            'world_xy': list(row['world_xy']), 'inspection_radius_m': 12,
            'inside_ground': ground.covers(point),
            'inside_allowed_road_mask': allowed_road.covers(point),
            'old_joined_road_covers_gate': road.covers(point),
            'new_joined_road_covers_gate': new_road.covers(point),
            'nearest_joined_road_before_m': road.distance(point),
            'nearest_joined_road_after_m': new_road.distance(point),
            'nearby_removed_road_area_m2': road_changed,
            'nearby_removed_curb_area_m2': curb_changed,
            'scope': 'Nearest distance refers only to this Joined road object; other campus road meshes and gate navigation are not inferred'})

    diagnostic_point = Point(249.10, 111.05)
    assert road.covers(diagnostic_point) and allowed_road.covers(diagnostic_point)
    assert removed_road.covers(diagnostic_point) and not new_road.covers(diagnostic_point)
    diagnostic = {'world_xy': list(diagnostic_point.coords[0]),
        'ground_contains': ground.covers(diagnostic_point),
        'distance_to_ground_m': ground.distance(diagnostic_point),
        'before_road_covers': True, 'allowed_mask_covers': True,
        'removed_road_covers': True, 'after_road_covers': False,
        'source': 'Previously observed grey-band point independently mapped from the retained preview camera'}

    piece = next(part for part in _parts(removed_road) if part.covers(diagnostic_point))
    local = piece.intersection(box(249.10 - 70, 111.05 - 55, 249.10 + 70, 111.05 + 55))
    seam = nearest_points(diagnostic_point, old_contact if not old_contact.is_empty else ground.boundary)[1]
    seam_window = box(seam.x - 65, seam.y - 50, seam.x + 65, seam.y + 50)
    seam_features = road.union(removed_curbs).intersection(seam_window)
    assert not local.is_empty and not seam_features.is_empty

    def frame(key, shape, description):
        x0, y0, x1, y1 = shape.bounds; pad = 8
        return {'key': key,
            'source_keys': sorted(name for name, source in source_shapes.items()
                                  if source.intersection(shape).area > tolerance),
            'source_world_frame': [[x0-pad, y0-pad, .35], [x1+pad, y0-pad, .35],
                                   [x1+pad, y1+pad, .35], [x0-pad, y1+pad, .35]],
            'frame_method': description + '; actual feature bounds plus 8m viewing padding, same world frame for before/current'}

    assert original == [_sha(shape) for shape in (road, curbs, ground)]
    checks = {'status': 'passed',
        'method': 'Subtract only original traced context-road buffers outside fixed modeled ground; subtract a ground-excluded 0.25m expansion of that mask from the old curb, without generating transverse cut-end curbs',
        'source_road_names': names, 'source_roads': source_records,
        'protected_connector_source_roads': connector_records,
        'connector_protection': {
            'context_outside_ground_mask_sha256': _sha(context_outside_ground),
            'source_noncontext_road_union_sha256': _sha(connector_union),
            'source_noncontext_curb_protection_sha256': _sha(connector_curb_protection),
            'old_external_context_overlap_with_noncontext_roads_m2': connector_overlap.area,
            'removed_noncontext_road_area_m2': connector_road_loss,
            'removed_noncontext_curb_area_m2': connector_curb_loss,
            'source_noncontext_road_count': len(connector_records),
            'method': 'Protect all non-context D.roads buffers made with exactly their original gp points, width, round joins and round caps; protect their old curb neighbourhood with the original 0.25m curb width'},
        'curb_removal_buffer_m': .25, 'road': road_checks, 'curb': curb_checks,
        'campus_connectivity': connectivity, 'gates': gate_checks,
        'diagnostic': diagnostic,
        'new_transverse_curb_area_m2': new_curbs.difference(curbs).area,
        'curb_recipe': 'old curb minus allowed_road_mask.buffer(0.25).difference(ground).difference(noncontext_road_union.buffer(0.25))',
        'comparison_frames': [frame('external-grey-band', local,
            'Removed component containing the diagnostic point, clipped to its 140x110m source neighbourhood'),
            frame('campus-road-seam', seam_features,
            'Old road/curb features within 130x100m of the nearest actual ground-boundary road contact')],
        'input_geometry_sha256': {'road': original[0], 'curb': original[1], 'ground': original[2]},
        'output_geometry_sha256': {'road': _sha(new_road), 'curb': _sha(new_curbs)},
        'removed_geometry_sha256': {'road': _sha(removed_road), 'curb': _sha(removed_curbs)},
        'source_inputs_unchanged': True,
        'fingerprint_method': 'SHA256 of Shapely normalized 2D little-endian WKB; no object allocation names',
        'limitations': 'Source-classified exterior-road depiction only. All campus-only road geometry and fixed gate neighbourhoods are preserved; this is not surveyed navigation, driving clearance or proof of routes beyond the modeled road object.'}
    return new_road, new_curbs, checks


def verify_context_meshes(road, curbs, faces_world):
    """Audit actual world-space faces supplied after the two meshes exist."""
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    expected = {'Joined continuous source roads': (road, .35),
                'Joined continuous road curbs': (curbs, .38)}
    assert set(faces_world) == set(expected)
    checks = {}
    for name, (footprint, z) in expected.items():
        faces = faces_world[name]
        assert faces and all(len(face) == 3 for face in faces), name
        height_error = max(abs(point[2] - z) for face in faces for point in face)
        assert height_error < 1e-6, (name, height_error)
        triangles = [Polygon([point[:2] for point in face]) for face in faces]
        assert all(triangle.is_valid or triangle.area <= 1e-10 for triangle in triangles)
        valid = [triangle for triangle in triangles if triangle.is_valid and triangle.area > 1e-10]
        assert valid, name
        actual = unary_union(valid)
        extra = actual.difference(footprint.buffer(.0002)).area
        missing = footprint.difference(actual.buffer(.0002)).area
        assert extra < 1e-7 and missing < 1e-7, (name, extra, missing)
        checks[name] = {'world_z_m': z, 'maximum_height_error_m': height_error,
            'triangle_count': len(faces), 'actual_area_m2': actual.area,
            'degenerate_or_zero_area_triangle_count': len(triangles) - len(valid),
            'actual_outside_expected_buffer_area_m2': extra,
            'expected_missing_from_actual_buffer_area_m2': missing,
            'numeric_planar_buffer_m': .0002,
            'expected_geometry_sha256': _sha(footprint),
            'actual_geometry_sha256': _sha(actual),
            'actual_covers_grey_band_diagnostic': actual.covers(Point(249.10, 111.05))}
    assert not checks['Joined continuous source roads']['actual_covers_grey_band_diagnostic']
    return checks
