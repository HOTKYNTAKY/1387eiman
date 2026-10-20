import * as THREE from 'three';

/**
 * AETHER — cinematic WebGL scene.
 * A shader-displaced morphing core + orbital rings + particle constellations,
 * driven by scroll state (tweened externally by GSAP) and cursor parallax.
 * Adaptive quality: DPR caps, particle budgets, auto-degrades on low FPS.
 */

const NOISE_GLSL = /* glsl */ `
vec3 mod289(vec3 x){return x - floor(x * (1.0/289.0)) * 289.0;}
vec4 mod289(vec4 x){return x - floor(x * (1.0/289.0)) * 289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}
float snoise(vec3 v){
  const vec2 C = vec2(1.0/6.0, 1.0/3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i  = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(
      i.z + vec4(0.0, i1.z, i2.z, 1.0))
      + i.y + vec4(0.0, i1.y, i2.y, 1.0))
      + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s1 = floor(b0)*2.0 + 1.0;
  vec4 s2 = floor(b1)*2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s1.xzyw*sh.xxyy;
  vec4 a1 = b1.xzyw + s2.xzyw*sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}
`;

const VERT = /* glsl */ `
uniform float uTime;
uniform float uDistort;
uniform float uFreq;
varying float vElev;
varying vec3 vNormal;
varying vec3 vView;
${NOISE_GLSL}
void main(){
  float n = snoise(position * uFreq + vec3(uTime * 0.16));
  float n2 = snoise(position * (uFreq * 2.3) - vec3(uTime * 0.11)) * 0.35;
  float elev = (n + n2) * uDistort;
  vec3 displaced = position + normal * elev;
  vElev = elev;
  vec4 mv = modelViewMatrix * vec4(displaced, 1.0);
  vNormal = normalize(normalMatrix * normal);
  vView = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}
`;

const FRAG = /* glsl */ `
uniform vec3 uColorA;
uniform vec3 uColorB;
uniform vec3 uColorC;
uniform float uTime;
uniform float uDim;
varying float vElev;
varying vec3 vNormal;
varying vec3 vView;
void main(){
  float fresnel = pow(1.0 - abs(dot(normalize(vNormal), normalize(vView))), 2.4);
  float t = smoothstep(-0.55, 0.85, vElev);
  vec3 col = mix(uColorA, uColorB, t);
  col = mix(col, uColorC, fresnel * 0.9);
  col += fresnel * 0.35 * uColorB;
  col += vec3(0.015, 0.015, 0.03);
  col *= uDim;
  gl_FragColor = vec4(col, 1.0);
}
`;

/* Colour palettes the core morphs through while scrolling */
const PALETTES = [
  { a: new THREE.Color('#0b0620'), b: new THREE.Color('#6d5cff'), c: new THREE.Color('#5ee7ff') },
  { a: new THREE.Color('#160b02'), b: new THREE.Color('#d8b46a'), c: new THREE.Color('#ff8a5c') },
  { a: new THREE.Color('#02141a'), b: new THREE.Color('#13b8c9'), c: new THREE.Color('#8b7bff') },
  { a: new THREE.Color('#12060f'), b: new THREE.Color('#c65cff'), c: new THREE.Color('#ffd95e') },
];

function makeParticles(count, radiusMin, radiusMax, color, size, opacity) {
  const pos = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const r = radiusMin + Math.random() * (radiusMax - radiusMin);
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.72;
    pos[i * 3 + 2] = r * Math.cos(phi);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.PointsMaterial({
    color, size, transparent: true, opacity,
    blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
  });
  return new THREE.Points(geo, mat);
}

export function createAetherScene(canvas, { reducedMotion = false } = {}) {
  if (reducedMotion) return null;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas, antialias: true, alpha: true, powerPreference: 'high-performance',
    });
  } catch (e) {
    return null;
  }

  const isSmall = Math.min(window.innerWidth, window.innerHeight) < 760;
  const DPR_STEPS = isSmall ? [1.5, 1.2, 1] : [1.75, 1.4, 1.1, 1];
  let dprIndex = 0;
  const setDpr = () => renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, DPR_STEPS[dprIndex]));
  setDpr();
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x050508, 0.055);

  const camera = new THREE.PerspectiveCamera(42, window.innerWidth / window.innerHeight, 0.1, 100);
  camera.position.set(0, 0, 8.2);

  const group = new THREE.Group();
  scene.add(group);

  /* — Morphing core — */
  const uniforms = {
    uTime: { value: 0 },
    uDistort: { value: 0.42 },
    uFreq: { value: 0.85 },
    uDim: { value: 1 },
    uColorA: { value: PALETTES[0].a.clone() },
    uColorB: { value: PALETTES[0].b.clone() },
    uColorC: { value: PALETTES[0].c.clone() },
  };
  const core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.85, isSmall ? 24 : 40),
    new THREE.ShaderMaterial({ uniforms, vertexShader: VERT, fragmentShader: FRAG })
  );
  group.add(core);

  /* Responsive framing — on portrait phones pull the camera back, shrink
     and lift the group, and dim the core so it never swallows the UI. */
  const fit = { zMul: 1, sMul: 1, yOff: 0 };
  const computeFit = () => {
    const a = window.innerWidth / window.innerHeight;
    if (a < 1) {
      fit.zMul = THREE.MathUtils.clamp(0.95 / a, 1.15, 1.6);
      fit.sMul = THREE.MathUtils.clamp(a + 0.28, 0.68, 0.9);
      fit.yOff = 0.55;
      uniforms.uDim.value = 0.78;
    } else {
      fit.zMul = 1; fit.sMul = 1; fit.yOff = 0;
      uniforms.uDim.value = 1;
    }
  };
  computeFit();

  /* Wireframe aura shell */
  const aura = new THREE.Mesh(
    new THREE.IcosahedronGeometry(2.35, 3),
    new THREE.MeshBasicMaterial({ color: 0x8b7bff, wireframe: true, transparent: true, opacity: 0.07 })
  );
  group.add(aura);

  /* — Orbital rings (physically lit → dynamic lighting) — */
  const ringMat = new THREE.MeshStandardMaterial({
    color: 0xd8b46a, metalness: 0.9, roughness: 0.28, emissive: 0x33240a, emissiveIntensity: 0.7,
  });
  const ring1 = new THREE.Mesh(new THREE.TorusGeometry(3.05, 0.022, 12, 220), ringMat);
  ring1.rotation.set(Math.PI / 2.4, 0.4, 0);
  const ring2 = new THREE.Mesh(new THREE.TorusGeometry(3.55, 0.014, 12, 220),
    new THREE.MeshStandardMaterial({ color: 0x9fd8ff, metalness: 0.9, roughness: 0.32, emissive: 0x0a2433, emissiveIntensity: 0.7 }));
  ring2.rotation.set(Math.PI / 1.8, -0.5, 0.4);
  group.add(ring1, ring2);

  /* — Particle constellations — */
  const starsNear = makeParticles(isSmall ? 450 : 1100, 3.2, 7.5, 0xd8c491, 0.035, 0.85);
  const starsFar = makeParticles(isSmall ? 700 : 1800, 6, 16, 0x7f9cff, 0.05, 0.55);
  scene.add(starsNear, starsFar);

  /* — Lights — */
  scene.add(new THREE.AmbientLight(0x333344, 1.4));
  const keyLight = new THREE.PointLight(0xd8b46a, 60, 30);
  keyLight.position.set(4, 3, 5);
  scene.add(keyLight);
  const rimLight = new THREE.PointLight(0x6d5cff, 45, 30);
  rimLight.position.set(-5, -2, 3);
  scene.add(rimLight);

  /* Externally-animated scroll state (GSAP tweens these numbers) */
  const state = {
    distort: 0.42,   // shader displacement amount
    freq: 0.85,      // noise frequency
    palette: 0,      // 0..3 interpolated palette index
    posX: 0, posY: 0,
    scale: 1,
    camZ: 8.2,
    spin: 1,         // rotation speed multiplier
  };

  /* Cursor parallax (smoothed) */
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  const onPointer = (e) => {
    pointer.tx = (e.clientX / window.innerWidth) * 2 - 1;
    pointer.ty = (e.clientY / window.innerHeight) * 2 - 1;
  };
  window.addEventListener('pointermove', onPointer, { passive: true });

  const onResize = () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    setDpr();
    computeFit();
  };
  window.addEventListener('resize', onResize);

  /* Render loop with adaptive quality + visibility pause */
  const tmpA = new THREE.Color(), tmpB = new THREE.Color(), tmpC = new THREE.Color();
  const clock = new THREE.Clock();
  let raf = 0, running = true, frameCount = 0, slowTime = 0;

  const applyPalette = (p) => {
    const i = Math.max(0, Math.min(PALETTES.length - 2, Math.floor(p)));
    const f = THREE.MathUtils.clamp(p - i, 0, 1);
    const A = PALETTES[i], B = PALETTES[i + 1];
    uniforms.uColorA.value.copy(tmpA.lerpColors(A.a, B.a, f));
    uniforms.uColorB.value.copy(tmpB.lerpColors(A.b, B.b, f));
    uniforms.uColorC.value.copy(tmpC.lerpColors(A.c, B.c, f));
    rimLight.color.copy(uniforms.uColorB.value);
  };

  const tick = () => {
    raf = requestAnimationFrame(tick);
    const dt = Math.min(clock.getDelta(), 0.05);
    const t = clock.elapsedTime;

    /* adaptive DPR: degrade if sustained slow frames */
    if (dt > 0.026) { slowTime += dt; } else { slowTime = Math.max(0, slowTime - dt); }
    if (slowTime > 1.2 && dprIndex < DPR_STEPS.length - 1) { dprIndex++; setDpr(); slowTime = 0; }
    frameCount++;

    pointer.x += (pointer.tx - pointer.x) * 0.045;
    pointer.y += (pointer.ty - pointer.y) * 0.045;

    uniforms.uTime.value = t;
    uniforms.uDistort.value += (state.distort - uniforms.uDistort.value) * 0.06;
    uniforms.uFreq.value += (state.freq - uniforms.uFreq.value) * 0.06;
    applyPalette(state.palette);

    core.rotation.y = t * 0.12 * state.spin;
    core.rotation.x = Math.sin(t * 0.1) * 0.18;
    aura.rotation.y = -t * 0.05;
    aura.rotation.z = t * 0.03;
    ring1.rotation.z = t * 0.08 * state.spin;
    ring2.rotation.z = -t * 0.06 * state.spin;
    starsNear.rotation.y = t * 0.02;
    starsFar.rotation.y = -t * 0.008;

    group.position.x += (state.posX - group.position.x) * 0.05;
    group.position.y += (state.posY + fit.yOff - group.position.y) * 0.05;
    const s = THREE.MathUtils.lerp(group.scale.x, state.scale * fit.sMul, 0.05);
    group.scale.setScalar(s);
    group.rotation.y = pointer.x * 0.28;
    group.rotation.x = pointer.y * 0.18;

    camera.position.x = pointer.x * 0.65;
    camera.position.y = -pointer.y * 0.45;
    camera.position.z += (state.camZ * fit.zMul - camera.position.z) * 0.05;
    camera.lookAt(0, 0, 0);

    keyLight.position.x = pointer.x * 6;
    keyLight.position.y = -pointer.y * 4 + 1.5;

    renderer.render(scene, camera);
  };
  tick();

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { cancelAnimationFrame(raf); running = false; clock.getDelta(); }
    else if (!running) { running = true; clock.getDelta(); tick(); }
  });

  return { state, scene, camera, renderer };
}
