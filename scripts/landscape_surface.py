"""Metre-based turf detail on the four retained geographic lawn finishes.

The source pigment and boundary shader remain connected. This late pass only
changes the lawn BSDF colour/normal/roughness; no surveyed mesh is displaced.
Patch scales, tint and relief are display estimates, not a planting survey.
"""
import bpy


def add_landscape_surface(state):
    digest, graph = state['lake_digest'], state['facade_graph_state']
    materials = state['meadow_materials']
    assert len(materials) == 4
    geometry = state['spatial_mesh_snapshot'](o for o in state['s'].objects
        if o.type == 'MESH' and not o.hide_render)
    old = {m.name: graph(m.node_tree) for m in materials}
    other = {m.name: digest(graph(m.node_tree)) for m in bpy.data.materials
        if m.use_nodes and m not in materials}
    world = digest(graph(state['s'].world.node_tree))
    roof = digest(state['faces'])
    recipes = []
    for material in materials:
        ns, links = material.node_tree.nodes, material.node_tree.links
        bs = ns.get('Principled BSDF')
        original = bs.inputs['Base Color'].links[0].from_socket
        original_normal = bs.inputs['Normal'].links[0].from_socket

        def node(kind, name):
            ob = ns.new(kind)
            ob.name = 'Landscape turf ' + name
            return ob

        coordinates = node('ShaderNodeNewGeometry', 'world metres')
        broad = node('ShaderNodeTexNoise', 'eight metre variation')
        broad.inputs['Scale'].default_value = .12
        broad.inputs['Detail'].default_value = 3
        broad.inputs['Roughness'].default_value = .68
        links.new(coordinates.outputs['Position'], broad.inputs['Vector'])
        patches = node('ShaderNodeValToRGB', 'restrained patch contrast')
        patches.color_ramp.elements[0].position = .22
        patches.color_ramp.elements[0].color = (.70, .75, .65, 1)
        patches.color_ramp.elements[1].position = .78
        patches.color_ramp.elements[1].color = (1.13, 1.10, 1.03, 1)
        links.new(broad.outputs['Fac'], patches.inputs[0])
        patch_colour = node('ShaderNodeMixRGB', 'retained geographic colour')
        patch_colour.blend_type = 'MULTIPLY'
        patch_colour.inputs[0].default_value = .72
        links.new(original, patch_colour.inputs[1])
        links.new(patches.outputs['Color'], patch_colour.inputs[2])
        pigment = node('ShaderNodeHueSaturation', 'soft olive pigment')
        pigment.inputs['Saturation'].default_value = .86
        pigment.inputs['Value'].default_value = .95
        links.new(patch_colour.outputs[0], pigment.inputs['Color'])
        medium = node('ShaderNodeTexNoise', 'one metre tufts')
        medium.inputs['Scale'].default_value = .85
        medium.inputs['Detail'].default_value = 2.6
        medium.inputs['Roughness'].default_value = .72
        links.new(coordinates.outputs['Position'], medium.inputs['Vector'])
        tufts = node('ShaderNodeValToRGB', 'tuft highlights')
        tufts.color_ramp.elements[0].position = .28
        tufts.color_ramp.elements[0].color = (.62, .68, .57, 1)
        tufts.color_ramp.elements[1].position = .72
        tufts.color_ramp.elements[1].color = (1.20, 1.20, 1.11, 1)
        links.new(medium.outputs['Fac'], tufts.inputs[0])
        surface = node('ShaderNodeMixRGB', 'tuft colour')
        surface.blend_type = 'MULTIPLY'
        surface.inputs[0].default_value = .45
        links.new(pigment.outputs[0], surface.inputs[1])
        links.new(tufts.outputs['Color'], surface.inputs[2])
        links.new(surface.outputs[0], bs.inputs['Base Color'])
        blades = node('ShaderNodeTexNoise', 'fine blades')
        blades.inputs['Scale'].default_value = 5.5
        blades.inputs['Detail'].default_value = 2
        links.new(coordinates.outputs['Position'], blades.inputs['Vector'])
        tuft_normal = node('ShaderNodeBump', 'tuft normals')
        tuft_normal.inputs['Strength'].default_value = .34
        tuft_normal.inputs['Distance'].default_value = .035
        links.new(medium.outputs['Fac'], tuft_normal.inputs['Height'])
        links.new(original_normal, tuft_normal.inputs['Normal'])
        blade_normal = node('ShaderNodeBump', 'blade normals')
        blade_normal.inputs['Strength'].default_value = .22
        blade_normal.inputs['Distance'].default_value = .014
        links.new(blades.outputs['Fac'], blade_normal.inputs['Height'])
        links.new(tuft_normal.outputs['Normal'], blade_normal.inputs['Normal'])
        links.new(blade_normal.outputs['Normal'], bs.inputs['Normal'])
        roughness = node('ShaderNodeMapRange', 'matte roughness')
        roughness.clamp = True
        roughness.inputs['To Min'].default_value = .90
        roughness.inputs['To Max'].default_value = .98
        links.new(blades.outputs['Fac'], roughness.inputs['Value'])
        links.new(roughness.outputs['Result'], bs.inputs['Roughness'])
        current = graph(material.node_tree)
        assert old[material.name]['nodes'] == [r for r in current['nodes']
            if not r['name'].startswith('Landscape turf ')]
        assert all(edge in current['links'] for edge in old[material.name]['links']
            if not (edge[2] == bs.name and edge[3] in {'Base Color', 'Normal', 'Roughness'}))
        recipes.append({'material': material.name,
            'input_graph_sha256': digest(old[material.name]),
            'output_graph_sha256': digest(current)})
    assert geometry == state['spatial_mesh_snapshot'](state['s'].objects[n] for n in geometry)
    assert other == {n: digest(graph(bpy.data.materials[n].node_tree)) for n in other}
    assert world == digest(graph(state['s'].world.node_tree)) and roof == digest(state['faces'])
    displacement_links = sum(link.to_socket.name == 'Displacement'
        for material in materials for link in material.node_tree.links)
    assert displacement_links == 0
    return {'material_count': 4, 'recipes': recipes,
        'broad_noise_scale_inverse_m_estimate': .12,
        'tuft_noise_scale_inverse_m_estimate': .85,
        'blade_noise_scale_inverse_m_estimate': 5.5,
        'patch_mix_estimate': .72, 'tuft_mix_estimate': .45,
        'saturation_estimate': .86, 'value_estimate': .95,
        'roughness_range_estimate': [.90, .98],
        'new_geometry_count': 0, 'displacement_link_count': displacement_links,
        'existing_visible_meshes_preserved': True,
        'existing_visible_mesh_count': len(geometry),
        'existing_visible_mesh_sha256': digest(geometry),
        'source_pigment_and_boundary_shader_preserved': True,
        'other_existing_material_graphs_preserved': True,
        'other_existing_material_graphs_sha256': digest(other),
        'world_and_roof_faces_preserved': True,
        'world_graph_sha256': world, 'roof_faces_sha256': roof}
