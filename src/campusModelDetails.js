import * as THREE from 'three'
import footprints from '../model/central-campus/footprints.json'
import centralReference from '../model/central-campus/references/satellite-export.json'
import campusReference from '../model/campus/references/satellite-export.json'

// Railings and bank finish are an interpretation of campus-aerial.jpg, not surveyed dimensions.
// Reuses the existing L01 shoreline; no new lake or road outline is introduced.
export function addLakeFinish(model) {
  const c = centralReference.extent, e = campusReference.extent, scale = Math.cos(31.578 * Math.PI / 180)
  const ox=e.xmin+600/1152*(e.xmax-e.xmin), oy=e.ymax-850/1920*(e.ymax-e.ymin)
  const shoreline=footprints.features.find(f=>f.id.startsWith('L01')).pixel_outline.map(([x,y])=>new THREE.Vector3((c.xmin+x/1800*(c.xmax-c.xmin)-ox)*scale,.2,-(c.ymax-y/1400*(c.ymax-c.ymin)-oy)*scale))
  if(shoreline[0].distanceTo(shoreline.at(-1))<.01) shoreline.pop()
  const group = new THREE.Group(); group.name='Central shoreline surface finish'
  group.userData.source='Existing L01 trace; aerial photograph supports bank and railing, dimensions interpreted'
  const railMaterial = new THREE.MeshStandardMaterial({color:'#d0d2bd',roughness:.65,metalness:.15})
  const postGeo = new THREE.BoxGeometry(.11,.86,.11)
  const posts=[]
  for(let i=0;i<shoreline.length;i++) {
    const a=shoreline[i],b=shoreline[(i+1)%shoreline.length],length=a.distanceTo(b)
    const count=Math.max(1,Math.floor(length/3.5))
    for(let j=0;j<count;j++) posts.push(a.clone().lerp(b,j/count))
  }
  const railPosts=new THREE.InstancedMesh(postGeo,railMaterial,posts.length),matrix=new THREE.Matrix4()
  posts.forEach((p,i)=>railPosts.setMatrixAt(i,matrix.makeTranslation(p.x,.65,p.z)))
  railPosts.castShadow=true;group.add(railPosts)
  // Low mineral edge follows the traced polygon. Existing paving and water remain in place.
  const vertices=[],indices=[]
  for(let i=0;i<shoreline.length;i++) {
    const a=shoreline[i],b=shoreline[(i+1)%shoreline.length],d=b.clone().sub(a).normalize(),n=new THREE.Vector3(-d.z,0,d.x).multiplyScalar(.12)
    const k=vertices.length/3
    for(const p of [a.clone().add(n),b.clone().add(n),b.clone().sub(n),a.clone().sub(n)]) vertices.push(p.x,.59,p.z)
    indices.push(k,k+1,k+2,k,k+2,k+3)
  }
  const edgeGeo=new THREE.BufferGeometry();edgeGeo.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));edgeGeo.setIndex(indices);edgeGeo.computeVertexNormals()
  const edge=new THREE.Mesh(edgeGeo,new THREE.MeshStandardMaterial({color:'#d5c9ae',side:THREE.DoubleSide,roughness:.95}));edge.receiveShadow=true;group.add(edge)
  model.add(group)
}
