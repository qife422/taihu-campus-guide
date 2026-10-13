import * as THREE from 'three'
import groundUrl from '../model/campus/references/satellite.jpg?url'
import northUrl from '../model/campus/references/north-extension.jpg?url'
import northReference from '../model/campus/references/north-extension.json'
import reference from '../model/campus/references/satellite-export.json'

// Visual interpretation from campus-aerial.jpg / teach6.jpg. No footprint changes.
const palette = {
  'Campus grass': '#6b934a', 'Turf light': '#679346', 'Turf dark': '#477c39',
  'Road asphalt': '#59615c', 'Pedestrian paving': '#c8c9b9',
  'Lake water': '#436e60', 'Red tiled roof': '#a95643',
  'Photo observed terracotta bands': '#b95f43', 'Warm mineral facade': '#d9cfb4',
  'Pale facade frame': '#eee9d7', 'Weathered flat roof': '#929c96',
  'Recessed blue glazing': '#456672', 'Recessed glass': '#3f5e65',
  'Photo observed solar array': '#294856', 'Dark roof tiles': '#555f59',
  'Concrete roof': '#a2a99d', 'Clay roof tiles': '#a8604c',
  'Athletics surface': '#b46751', 'Court green': '#4e9081',
  'Canopy 0': '#326331', 'Canopy 1': '#49782f', 'Canopy 2': '#668c39', 'Canopy 3': '#397545',
}

export function refineMaterials(root, invalidate, { preserveAuthored = false } = {}) {
  let active=true
  const ground = preserveAuthored ? null : new THREE.TextureLoader().load(groundUrl, () => { if(active) invalidate() })
  const north = preserveAuthored ? null : new THREE.TextureLoader().load(northUrl,()=>{if(active)invalidate()})
  for (const texture of [ground, north]) if (texture) { texture.colorSpace=THREE.SRGBColorSpace; texture.anisotropy=4 }
  const e=reference.extent,scale=Math.cos(31.578*Math.PI/180)
  const ox=e.xmin+600/1152*(e.xmax-e.xmin),oy=e.ymax-850/1920*(e.ymax-e.ymin)
  const ne=northReference.extent
  const northBounds=new THREE.Vector4((ne.xmin-ox)*scale,-(ne.ymax-oy)*scale,(ne.xmax-ne.xmin)*scale,(ne.ymax-ne.ymin)*scale)
  const bounds=new THREE.Vector4((e.xmin-ox)*scale,-(e.ymax-oy)*scale,(e.xmax-e.xmin)*scale,(e.ymax-e.ymin)*scale)
  for (const [texture,b,name] of [[ground,bounds,'Satellite ground context'],[north,northBounds,'Northern satellite context']]) {
    if (!texture) continue
    const sheet=new THREE.Mesh(new THREE.PlaneGeometry(b.z,b.w),new THREE.MeshStandardMaterial({map:texture,color:'#d2dbc2',roughness:1}))
    sheet.name=name;sheet.rotation.x=-Math.PI/2;sheet.position.set(b.x+b.z/2,-.25,b.y+b.w/2);sheet.receiveShadow=true;root.add(sheet)
  }
  const seen = new Set()
  root.traverse(obj => {
    if (!obj.isMesh) return
    for (const material of Array.isArray(obj.material) ? obj.material : [obj.material]) {
      if (seen.has(material)) continue
      seen.add(material)
      const name = material.name
      if (!preserveAuthored) {
        if (palette[name]) material.color.set(palette[name])
        if (/glaz|glass|solar/i.test(name)) { material.roughness = .3; material.metalness = .22 }
        else material.roughness = .88
      }
      const kind = /grass|Turf|lawn/i.test(name) ? 1 : /paving|flat roof|Concrete roof/.test(name) ? 2 : /tiled roof|roof tiles/.test(name) ? 3 : /Lake water/.test(name) ? 4 : /asphalt/.test(name) ? 5 : 0
      if (!kind) continue
      // World-space surface finish keeps detail stable at any zoom and needs no bitmap upscale.
      material.onBeforeCompile = shader => {
        shader.vertexShader = 'varying vec3 campusWorld;\n' + shader.vertexShader
        shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\ncampusWorld = (modelMatrix * vec4(position, 1.0)).xyz;')
        shader.uniforms.campusNorth={value:north};shader.uniforms.campusNorthBounds={value:northBounds};shader.uniforms.campusGround={value:ground};shader.uniforms.campusBounds={value:bounds}
        shader.fragmentShader = `uniform sampler2D campusNorth; uniform vec4 campusNorthBounds; uniform sampler2D campusGround; uniform vec4 campusBounds; varying vec3 campusWorld;
          float campusHash(vec2 p) { return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
          float campusNoise(vec2 p) { vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f); return mix(mix(campusHash(i),campusHash(i+vec2(1,0)),f.x),mix(campusHash(i+vec2(0,1)),campusHash(i+vec2(1,1)),f.x),f.y); }
        ` + shader.fragmentShader
        const finish = kind === 1 ? 'float finish = .83 + .18 * campusNoise(campusWorld.xz * .12) + .09 * campusNoise(campusWorld.xz * 2.0);'
          : kind === 2 ? 'vec2 grid = abs(fract(campusWorld.xz / 1.6)-.5); float seam = smoothstep(.46,.5,max(grid.x,grid.y)); float finish = .96 - seam*.11 + campusNoise(campusWorld.xz * 8.0)*.04;'
          : kind === 3 ? 'float tile = smoothstep(.43,.5,abs(fract(campusWorld.x*.95)-.5)); float finish = .91 - tile*.10 + .10*campusNoise(campusWorld.xz*2.5);'
          : kind === 4 ? 'float finish = .90 + .13*campusNoise(campusWorld.xz*.10) + .035*sin(campusWorld.x*2.0+campusWorld.z*.7);'
          : 'float finish = .91 + .09*campusNoise(campusWorld.xz*5.0);'
        shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>', '#include <color_fragment>\n' + finish + '\ndiffuseColor.rgb *= finish;' + (!preserveAuthored && name === 'Campus grass' ? '\nvec2 uvGround=(campusWorld.xz-campusBounds.xy)/campusBounds.zw; if(all(greaterThanEqual(uvGround,vec2(0.0))) && all(lessThanEqual(uvGround,vec2(1.0)))) { vec3 observed=texture2D(campusGround,vec2(uvGround.x,1.0-uvGround.y)).rgb; diffuseColor.rgb=mix(diffuseColor.rgb,observed,0.68); } else { vec2 uvNorth=(campusWorld.xz-campusNorthBounds.xy)/campusNorthBounds.zw; if(all(greaterThanEqual(uvNorth,vec2(0.0))) && all(lessThanEqual(uvNorth,vec2(1.0)))) { diffuseColor.rgb=mix(diffuseColor.rgb,texture2D(campusNorth,vec2(uvNorth.x,1.0-uvNorth.y)).rgb,0.68); } }' : ''))
      }
      material.customProgramCacheKey = () => `campus-finish-${kind}-${name === 'Campus grass'}-${preserveAuthored}`
      material.needsUpdate = true
    }
  })
  return () => { active=false;ground?.dispose();north?.dispose() }
}

export function foliageGeometry(seed = 0) {
  const geometry = new THREE.IcosahedronGeometry(1, 2)
  const points = geometry.attributes.position
  for (let i=0;i<points.count;i++) {
    const x=points.getX(i),y=points.getY(i),z=points.getZ(i)
    const radius=1 + .14*Math.sin(x*17+seed)*Math.sin(y*13+seed)*Math.sin(z*19)
    points.setXYZ(i,x*radius,y*radius,z*radius)
  }
  geometry.computeVertexNormals()
  return geometry
}
