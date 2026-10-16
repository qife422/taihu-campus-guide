"""Make the single current before/after atlas comparison, without rendering.

Run with /opt/anaconda3/bin/python -B scripts/compare_landscape_atlas.py after
the complete candidate WebP and metadata exist in /tmp/taihu-full. Inputs are
the retained iteration-baseline pair and the current campus-atlas pair. Only
the stable comparison poster and iteration-comparison.json are replaced.
"""
from pathlib import Path
import hashlib
import io
import json
import math
import os
import tempfile

from PIL import Image, ImageDraw, ImageFont, __version__ as PILLOW_VERSION


ROOT = Path(__file__).resolve().parents[1]
CACHE = Path('/tmp/taihu-full')
POSTER = ROOT/'output/playwright/landscape-comparison.webp'
MANIFEST = CACHE/'iteration-comparison.json'
SIZE = (7168, 3072)
MIDDLE_IDS = [f'M{i:02}' for i in range(1, 8)]
COURT_ID = 'M field pedestrian wedge'
MAX_PANEL = (840, 620)
CROP_PADDING_PX = 28
DIRECTORY_LIMIT = 192*1024**2
POSTER_LIMIT = 2*1024**2
FONT_PATH = Path('/System/Library/Fonts/Supplemental/Arial.ttf')


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def digest(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def load_atlas(metadata_path, image_path):
    metadata_bytes, image_bytes = metadata_path.read_bytes(), image_path.read_bytes()
    metadata = json.loads(metadata_bytes)
    assert (metadata['width'], metadata['height'], metadata['samples']) == (*SIZE, 16)
    assert metadata['image_sha256'] == sha(image_bytes), image_path
    assert metadata['image_bytes'] == len(image_bytes), image_path
    assert isinstance(metadata['sources'], dict) and metadata['sources']
    assert all(isinstance(path, str) and len(value) == 64 and set(value) <= set('0123456789abcdef')
               for path, value in metadata['sources'].items())
    with Image.open(io.BytesIO(image_bytes)) as source:
        assert source.format == 'WEBP' and source.size == SIZE
        image = source.convert('RGB')
    info = {'metadata': {'path': str(metadata_path), 'sha256': sha(metadata_bytes), 'bytes': len(metadata_bytes)},
            'image': {'path': str(image_path), 'sha256': sha(image_bytes), 'bytes': len(image_bytes)}}
    return metadata, image, info


def validate_pair(before, current):
    assert before['image_sha256'] != current['image_sha256'], 'Previous image is not a new candidate'
    assert before['camera'] == current['camera'], 'Camera changed; identical crop comparison is invalid'
    assert before['roof_faces_world'] == current['roof_faces_world']
    assert len(current['roof_faces_world']) == 130
    assert set(row['id'] for row in before['records']) == set(row['id'] for row in current['records'])
    centres = lambda meta: sorted(tuple(row[1]) for row in meta['landscape_revision']['tree_pairs'])
    assert centres(before) == centres(current) and len(centres(current)) == 1971
    check = current['checks']['paving_regularization']
    assert check['status'] == 'passed' and check['source_building_ids'] == MIDDLE_IDS
    assert 'scripts/paving_cleanup.py' in current['sources']
    for path, expected in current['sources'].items():
        assert sha((ROOT/path).read_bytes()) == expected, ('Candidate source changed', path)


def world_box(bounds, z_low, z_high):
    assert len(bounds) == 4 and all(math.isfinite(value) for value in [*bounds, z_low, z_high])
    x0, y0, x1, y1 = bounds
    assert x0 < x1 and y0 < y1 and z_low <= z_high
    return [[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in sorted({z_low, z_high})]


def project(point, camera):
    """Independent scalar orthographic projection, Rz*Ry*Rx camera rotation."""
    rx, ry, rz = camera['rotation_euler']
    sx, cx, sy, cy, sz, cz = math.sin(rx), math.cos(rx), math.sin(ry), math.cos(ry), math.sin(rz), math.cos(rz)
    x, y, z = [float(value)-camera['position'][i] for i, value in enumerate(point)]
    local_x = x*cz*cy+y*sz*cy-z*sy
    local_y = x*(cz*sy*sx-sz*cx)+y*(sz*sy*sx+cz*cx)+z*cy*sx
    pixels_per_metre = SIZE[0]/camera['ortho_scale']
    return [SIZE[0]/2+local_x*pixels_per_metre, SIZE[1]/2-local_y*pixels_per_metre]


def crop_region(frame, camera):
    pixels = [project(point, camera) for point in frame]
    assert pixels and all(math.isfinite(value) for point in pixels for value in point)
    bounds = [math.floor(min(p[0] for p in pixels))-CROP_PADDING_PX,
              math.floor(min(p[1] for p in pixels))-CROP_PADDING_PX,
              math.ceil(max(p[0] for p in pixels))+CROP_PADDING_PX,
              math.ceil(max(p[1] for p in pixels))+CROP_PADDING_PX]
    crop = [max(0, bounds[0]), max(0, bounds[1]), min(SIZE[0], bounds[2]), min(SIZE[1], bounds[3])]
    width, height = crop[2]-crop[0], crop[3]-crop[1]
    assert width > 0 and height > 0
    scale = min(1.0, MAX_PANEL[0]/width, MAX_PANEL[1]/height)
    panel = [max(1, math.floor(width*scale)), max(1, math.floor(height*scale))]
    assert panel[0] <= width and panel[1] <= height
    return {'native_pixel_crop': crop, 'panel_pixel_size': panel,
            'native_to_panel_scale': min(panel[0]/width, panel[1]/height),
            'native_to_panel_scale_xy': [panel[0]/width, panel[1]/height],
            'crop_padding_pixels': CROP_PADDING_PX, 'source_frame_clipped_at_image_edge': crop != bounds}


def select_regions(before, current):
    roof_points = [point for key in MIDDLE_IDS for face in current['roof_faces_world'][key] for point in face]
    building_bounds = [min(p[0] for p in roof_points), min(p[1] for p in roof_points),
                       max(p[0] for p in roof_points), max(p[1] for p in roof_points)]
    rows = lambda meta: [row for row in meta['checks']['landscape_detail']['courtyards']['sites']
                         if row['source_id'] == COURT_ID]
    old_court, new_court = rows(before), rows(current)
    assert len(old_court) == len(new_court) == 1
    old_court, new_court = old_court[0], new_court[0]
    assert old_court['source_world_bounds'] == new_court['source_world_bounds']
    assert old_court['source_paved_footprint_sha256'] == new_court['source_paved_footprint_sha256']
    assert old_court['source_pixels'] == new_court['source_pixels']
    court_bounds = new_court['source_world_bounds']
    assert len(court_bounds) == 5
    ground_z_high = max(0.0, float(court_bounds[4]))
    window = current['checks']['paving_regularization']['candidate_world_bounds']
    regions = [
        {'key': 'middle-paving-and-lawn', 'label': 'Middle buildings: paving meets retained lawn',
         'source_ids': MIDDLE_IDS, 'source_basis': 'Equal M01-M07 retained roof records and their ground-plane extent',
         'source_world_frame': world_box(building_bounds, 0.0, max(p[2] for p in roof_points))},
        {'key': 'paving-regularization-window', 'label': 'Bounded paving cleanup: full candidate window',
         'source_ids': MIDDLE_IDS, 'source_basis': 'checks.paving_regularization.candidate_world_bounds',
         'candidate_world_bounds': window, 'projection_z_range_m': [0.0, ground_z_high],
         'source_world_frame': world_box(window, 0.0, ground_z_high)},
        {'key': 'middle-retained-courtyard', 'label': 'Middle courtyard: retained source paving',
         'source_ids': [COURT_ID], 'source_basis': 'Equal retained middle courtyard source cap bounds and footprint hash',
         'source_object': new_court['source_object'],
         'source_footprint_sha256': new_court['source_paved_footprint_sha256'],
         'source_world_frame': world_box(court_bounds[:4], float(court_bounds[4]), float(court_bounds[4]))},
    ]
    for row in regions:
        row.update(crop_region(row['source_world_frame'], current['camera']))
    return regions


def make_poster(before_image, current_image, regions, image_hashes):
    font_file = FONT_PATH if FONT_PATH.is_file() else None
    def font(size):
        return ImageFont.truetype(str(font_file), size) if font_file else ImageFont.load_default(size=size)
    margin, gap, row_gap = 28, 24, 26
    panel_width = max(row['panel_pixel_size'][0] for row in regions)
    row_heights = [row['panel_pixel_size'][1]+104 for row in regions]
    width = margin*2+panel_width*2+gap
    height = 144+sum(row_heights)+row_gap*(len(regions)-1)+72
    poster = Image.new('RGB', (width, height), '#f1f1eb')
    draw = ImageDraw.Draw(poster)
    draw.text((margin, 20), 'Native atlas / middle paving comparison', font=font(28), fill='#23251f')
    draw.text((margin, 61), 'Same camera, source roofs and crop coordinates. No colour adjustment or pixel enlargement.',
              font=font(16), fill='#55594f')
    columns = [('BEFORE', before_image, image_hashes['before']),
               ('CANDIDATE', current_image, image_hashes['current'])]
    placements, y = [], 144
    for number, (region, row_height) in enumerate(zip(regions, row_heights), 1):
        draw.text((margin, y), str(number)+'  '+region['label'], font=font(22), fill='#23251f')
        crop = tuple(region['native_pixel_crop']); panel_size = tuple(region['panel_pixel_size'])
        row_places = []
        for column, (label, source, fingerprint) in enumerate(columns):
            left = margin+column*(panel_width+gap)
            draw.text((left, y+34), label+'  '+fingerprint[:16], font=font(15), fill='#55594f')
            tile = source.crop(crop)
            assert tile.width >= panel_size[0] and tile.height >= panel_size[1]
            if tile.size != panel_size:
                tile = tile.resize(panel_size, Image.Resampling.LANCZOS)
            box = [left, y+59, left+panel_width, y+59+panel_size[1]]
            draw.rectangle(box, fill='white')
            x = left+(panel_width-panel_size[0])//2
            poster.paste(tile, (x, y+59))
            row_places.append([x, y+59, x+panel_size[0], y+59+panel_size[1]])
        draw.text((margin, y+65+panel_size[1]),
                  'Native crop '+str(list(crop))+'  |  scale '+format(region['native_to_panel_scale'], '.4f'),
                  font=font(14), fill='#55594f')
        placements.append(row_places)
        y += row_height+row_gap
    draw.text((margin, height-48), 'Selected finish regions only. Different-campus reference parity is not claimed.',
              font=font(15), fill='#55594f')
    buffer = io.BytesIO()
    poster.save(buffer, format='WEBP', lossless=True, quality=100, method=6, exact=True)
    payload = buffer.getvalue()
    assert 0 < len(payload) < POSTER_LIMIT
    # Lossless WebP must retain every pasted RGB pixel, including downsampled
    # tiles. Labels and whitespace never cover the actual comparison crops.
    with Image.open(io.BytesIO(payload)) as decoded:
        restored = decoded.convert('RGB')
        assert restored.size == poster.size
        for region, positions in zip(regions, placements):
            for source, box in zip((before_image, current_image), positions):
                expected = source.crop(tuple(region['native_pixel_crop']))
                size = tuple(region['panel_pixel_size'])
                if expected.size != size:
                    expected = expected.resize(size, Image.Resampling.LANCZOS)
                assert restored.crop(tuple(box)).tobytes() == expected.tobytes()
    return payload, list(poster.size), {'pillow_version': PILLOW_VERSION,
        'font': str(font_file) if font_file else 'Pillow default font',
        'font_sha256': sha(font_file.read_bytes()) if font_file else None,
        'encoding': {'format': 'WEBP', 'lossless': True, 'quality': 100, 'method': 6},
        'panel_positions_before_current': placements,
        'decoded_crop_pixels_equal_preencoding_panels': True}


def manifest(before, current, input_info, regions, poster_payload, dimensions, rendering):
    return {'method': 'Crop previous and current formal WebP images through exactly equal camera/roof records; identical before/current crop coordinates, no colour adjustment, native-to-panel scale at most one; lossless comparison WebP.',
        'script': 'scripts/compare_landscape_atlas.py', 'script_sha256': sha(Path(__file__).read_bytes()),
        'input_image_sha256': {key: row['image']['sha256'] for key, row in input_info.items()},
        'input_image_paths': {key: row['image']['path'] for key, row in input_info.items()},
        'input_metadata': {key: row['metadata'] for key, row in input_info.items()},
        'input_image_bytes': {key: row['image']['bytes'] for key, row in input_info.items()},
        'input_source_collections': {'before': before['sources'], 'current': current['sources']},
        'input_source_collection_sha256': {'before': digest(before['sources']), 'current': digest(current['sources'])},
        'input_sizes': {'before': list(SIZE), 'current': list(SIZE)},
        'samples': 16, 'camera': current['camera'], 'camera_sha256': digest(current['camera']),
        'equal_source_roof_records_sha256': digest(current['roof_faces_world']),
        'regions': regions, 'rendering': rendering,
        'artifacts': [{'path': POSTER.relative_to(ROOT).as_posix(), 'sha256': sha(poster_payload),
                       'bytes': len(poster_payload), 'dimensions': dimensions}],
        'limitations': 'Source crops are selected presentation regions, not proof of unchanged pixels or botanical/architectural accuracy. Original source-tree name/prototype allocation can differ across native processes; separate native preservation records apply. The paving window is projected between ground Z=0 and the retained courtyard cap height; this frames the region, not an occlusion measurement. Metadata inputs are historical file fingerprints, not recursively embedded metadata or active temporary artifacts. Native protection and human visual inspection are separate gates. No reference parity is claimed.'}


def directory_bytes(path):
    return sum(item.stat().st_size for item in path.rglob('*') if item.is_file())


def atomic_replace(path, payload):
    # The only short-lived extra file is our own atomic-write temporary. An
    # interrupted prior image is never copied into a growing backup tree.
    with tempfile.NamedTemporaryFile(prefix='.'+path.name+'-', suffix='.tmp', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    before, before_image, before_info = load_atlas(CACHE/'iteration-baseline.json', CACHE/'iteration-baseline.webp')
    current, current_image, current_info = load_atlas(CACHE/'campus-atlas.json', CACHE/'campus-atlas.webp')
    validate_pair(before, current)
    regions = select_regions(before, current)
    hashes = {'before': before['image_sha256'], 'current': current['image_sha256']}
    payload, dimensions, rendering = make_poster(before_image, current_image, regions, hashes)
    record = manifest(before, current, {'before': before_info, 'current': current_info},
                      regions, payload, dimensions, rendering)
    encoded = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    assert POSTER.parent.is_dir() and CACHE.is_dir()
    assert directory_bytes(POSTER.parent)+len(payload) < DIRECTORY_LIMIT
    assert directory_bytes(CACHE)+len(encoded) < DIRECTORY_LIMIT
    # Finish all source, crop, pixel-readback and capacity checks before writes.
    atomic_replace(POSTER, payload)
    atomic_replace(MANIFEST, encoded)
    print(json.dumps({'status': 'comparison_generated_needs_visual_review',
        'input_image_sha256': hashes, 'region_count': len(regions),
        'poster': record['artifacts'][0], 'manifest': str(MANIFEST),
        'manifest_sha256': sha(encoded), 'manifest_bytes': len(encoded)}))


if __name__ == '__main__':
    main()
