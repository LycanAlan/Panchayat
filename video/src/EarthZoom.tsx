import React, { useMemo, useRef } from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing, staticFile } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import * as THREE from "three";
import { useLoader, useFrame } from "@react-three/fiber";

// Bengaluru, Ward 12: ~12.97N, 77.59E. Standard lat/lon -> unit-sphere vector
// for an equirectangular texture with the prime meridian at the texture's
// horizontal center (the convention this three.js example texture uses).
function latLonToVector3(lat: number, lon: number, radius: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

const PIN_LAT = 12.97;
const PIN_LON = 77.59;
const EARTH_RADIUS = 2;

// Sun stays fixed in world space; the earth/clouds rotate under it, which is
// what actually produces a moving terminator line (day/night edge) and lets
// the night-lights shader do its job instead of a static half-lit sphere.
const SUN_DIRECTION = new THREE.Vector3(1, 0.15, 0.6).normalize();

// ---------------------------------------------------------------- shaders

// Day/night blend on a soft terminator, day side lit normally (with an ocean
// specular highlight from the real specular mask), night side showing city
// lights instead of going flat black -- the single detail that reads as
// "a real planet" rather than "a lit sphere with a texture."
const earthVertexShader = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vWorldNormal;
  varying vec3 vViewDir;

  void main() {
    vUv = uv;
    vWorldNormal = normalize(mat3(modelMatrix) * normal);
    vec4 worldPosition = modelMatrix * vec4(position, 1.0);
    vViewDir = normalize(cameraPosition - worldPosition.xyz);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const earthFragmentShader = /* glsl */ `
  uniform sampler2D dayMap;
  uniform sampler2D nightMap;
  uniform sampler2D specularMap;
  uniform vec3 sunDirection;

  varying vec2 vUv;
  varying vec3 vWorldNormal;
  varying vec3 vViewDir;

  void main() {
    vec3 normal = normalize(vWorldNormal);
    float ndotl = dot(normal, sunDirection);

    // Soft terminator instead of a hard day/night line -- real satellite
    // photography always shows a gradient dusk band, not a knife edge.
    float dayMix = smoothstep(-0.15, 0.2, ndotl);

    vec3 dayColor = texture2D(dayMap, vUv).rgb;
    // Real night-lights photography is mostly near-black with sparse bright
    // pixels -- a flat multiply barely shows anything. A gamma lift (pow <1)
    // raises the dim glow around cities before the multiply boosts the
    // bright cores, which is what actually reads as "lit-up continent" like
    // real Black Marble imagery instead of a nearly empty black sphere.
    vec3 nightRaw = texture2D(nightMap, vUv).rgb;
    vec3 nightColor = pow(nightRaw, vec3(0.55)) * 1.35;

    float specMask = texture2D(specularMap, vUv).r; // bright on ocean, ~0 on land
    vec3 reflectDir = reflect(-sunDirection, normal);
    float specular = pow(max(dot(reflectDir, vViewDir), 0.0), 24.0) * specMask * dayMix;

    vec3 color = mix(nightColor, dayColor, dayMix) + specular * 0.6;
    gl_FragColor = vec4(color, 1.0);
  }
`;

const Earth: React.FC<{ rotation: number; pinPulse: number; pinScale?: number }> = ({ rotation, pinPulse, pinScale = 1 }) => {
  const [dayMap, nightMap, specularMap] = useLoader(THREE.TextureLoader, [
    staticFile("earth_day_8k.jpg"),
    staticFile("earth_night_8k.jpg"),
    staticFile("earth_specular_2048.jpg"),
  ]);
  const cloudMap = useLoader(THREE.TextureLoader, staticFile("earth_clouds_8k.jpg"));

  const pinPosition = useMemo(
    () => latLonToVector3(PIN_LAT, PIN_LON, EARTH_RADIUS * 1.012),
    [],
  );

  // Pulsing halo scale/opacity so the Bengaluru marker reads as a single
  // small bright "dot" even from full-globe distance -- a ping, not a sun --
  // before the camera commits to the zoom.
  const haloScale = 1 + pinPulse * 0.5;
  const haloOpacity = 0.4 * (1 - pinPulse * 0.7);

  const uniforms = useMemo(
    () => ({
      dayMap: { value: dayMap },
      nightMap: { value: nightMap },
      specularMap: { value: specularMap },
      sunDirection: { value: SUN_DIRECTION },
    }),
    [dayMap, nightMap, specularMap],
  );

  return (
    <group rotation={[0, rotation, 0]}>
      {/* The globe: custom day/night shader, not a flat lit texture. */}
      <mesh>
        <sphereGeometry args={[EARTH_RADIUS, 96, 96]} />
        <shaderMaterial
          vertexShader={earthVertexShader}
          fragmentShader={earthFragmentShader}
          uniforms={uniforms}
        />
      </mesh>

      {/* Cloud shell: real alpha-mapped cloud texture, rotating slightly
          faster than the surface for a drifting-weather parallax. */}
      <mesh rotation={[0, rotation * 0.6, 0]}>
        <sphereGeometry args={[EARTH_RADIUS * 1.015, 96, 96]} />
        <meshStandardMaterial
          map={cloudMap}
          transparent
          opacity={0.85}
          depthWrite={false}
        />
      </mesh>

      {/* Thin atmosphere rim glow. */}
      <mesh>
        <sphereGeometry args={[EARTH_RADIUS * 1.045, 64, 64]} />
        <meshBasicMaterial
          color="#4a90d9"
          transparent
          opacity={0.22}
          side={THREE.BackSide}
          blending={THREE.AdditiveBlending}
        />
      </mesh>

      {/* Bengaluru pin: small bright core + a subtle pulsing ping, sized to
          read as a single dot against the globe, not a second sun. */}
      <mesh position={pinPosition} scale={pinScale}>
        <sphereGeometry args={[0.02, 16, 16]} />
        <meshBasicMaterial color="#ffe9b0" />
      </mesh>
      <mesh position={pinPosition} scale={haloScale * pinScale}>
        <sphereGeometry args={[0.045, 20, 20]} />
        <meshBasicMaterial
          color="#ffb020"
          transparent
          opacity={haloOpacity}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
      <mesh position={pinPosition} scale={(1 + haloScale * 0.5) * pinScale}>
        <sphereGeometry args={[0.045, 20, 20]} />
        <meshBasicMaterial
          color="#ffb020"
          transparent
          opacity={haloOpacity * 0.35}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </group>
  );
};

// ------------------------------------------------------------ real stars

// Varied size, varied colour temperature (mostly white, some warm, a few
// blue-white), soft circular falloff instead of hard square dots -- the
// three things that separate "starfield" from "dots pasted on black."
const starVertexShader = /* glsl */ `
  attribute float aSize;
  attribute vec3 aColor;
  varying vec3 vColor;

  void main() {
    vColor = aColor;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    // Deliberately NOT distance-attenuated: real stars are near-infinitely
    // far away, so their apparent size does not change as this scene's
    // camera dollies a few units closer to the earth.
    gl_PointSize = aSize;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const starFragmentShader = /* glsl */ `
  varying vec3 vColor;

  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float d = length(uv);
    if (d > 0.5) discard;
    float glow = smoothstep(0.5, 0.0, d);
    gl_FragColor = vec4(vColor * glow, glow);
  }
`;

const Stars: React.FC = () => {
  const { positions, sizes, colors } = useMemo(() => {
    const count = 3500;
    const pos = new Float32Array(count * 3);
    const size = new Float32Array(count);
    const col = new Float32Array(count * 3);

    // Real star colour: mostly white, a warm minority (K/M-type), a cool
    // blue-white minority (O/B-type) -- matches actual stellar distribution
    // well enough to read as "real" rather than uniform white noise.
    const warm = new THREE.Color("#ffe3b0");
    const cool = new THREE.Color("#bcd2ff");
    const white = new THREE.Color("#ffffff");

    for (let i = 0; i < count; i++) {
      const r = 40 + Math.random() * 25;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = r * Math.cos(phi);

      // Most stars are small and dim; a few are noticeably bright -- a
      // skewed distribution, not uniform random, is what makes a starfield
      // look real instead of like graph paper.
      const magnitudeRoll = Math.random();
      size[i] = magnitudeRoll > 0.985 ? 5.5 + Math.random() * 2.5
        : magnitudeRoll > 0.9 ? 2.5 + Math.random() * 1.5
        : 1.0 + Math.random() * 1.2;

      const colorRoll = Math.random();
      const c = colorRoll < 0.08 ? warm : colorRoll < 0.16 ? cool : white;
      col[i * 3] = c.r;
      col[i * 3 + 1] = c.g;
      col[i * 3 + 2] = c.b;
    }
    return { positions: pos, sizes: size, colors: col };
  }, []);

  return (
    <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={positions.length / 3} array={positions} itemSize={3} />
        <bufferAttribute attach="attributes-aSize" count={sizes.length} array={sizes} itemSize={1} />
        <bufferAttribute attach="attributes-aColor" count={colors.length / 3} array={colors} itemSize={3} />
      </bufferGeometry>
      <shaderMaterial
        vertexShader={starVertexShader}
        fragmentShader={starFragmentShader}
        transparent
        depthWrite={false}
      />
    </points>
  );
};

type Shot = { startDistance: number; endDistance: number; holdFraction: number; spin: number; easeIn: boolean };
const DEFAULT_SHOT: Shot = { startDistance: 9, endDistance: EARTH_RADIUS * 1.35, holdFraction: 0.25, spin: Math.PI * 0.15, easeIn: true };

const CameraRig: React.FC<{ progress: number; rotation: number; shot: Shot }> = ({ progress, rotation, shot }) => {
  useFrame(({ camera }) => {
    const curve = shot.easeIn ? Easing.bezier(0.32, 0, 0.67, 0) : Easing.bezier(0.45, 0, 0.35, 1);
    const distance = interpolate(curve(progress), [0, 1], [shot.startDistance, shot.endDistance]);
    // Aim at where Bengaluru is NOW: the globe spins under the camera.
    const pin = latLonToVector3(PIN_LAT, PIN_LON, 1).applyAxisAngle(new THREE.Vector3(0, 1, 0), rotation);
    camera.position.copy(pin.clone().multiplyScalar(distance));
    camera.lookAt(0, 0, 0);
  });
  return null;
};

export const EarthZoom: React.FC<{ durationFrames?: number; shot?: Partial<Shot> }> = ({ durationFrames, shot: shotOverride }) => {
  const frame = useCurrentFrame();
  const { durationInFrames: compositionFrames, width, height, fps } = useVideoConfig();
  const durationInFrames = durationFrames ?? compositionFrames;
  const shot: Shot = { ...DEFAULT_SHOT, ...shotOverride };

  // Hold on the full globe first -- long enough to register India, then
  // Bengaluru, as a bright dot -- before the dolly-in starts.
  const holdFrames = Math.round(durationInFrames * shot.holdFraction);
  const zoomProgress = interpolate(
    frame,
    [holdFrames, durationInFrames - 1],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const rotation = interpolate(frame, [0, durationInFrames], [0, shot.spin]);

  // Keep the marker the same size on screen: it shrinks with the camera's
  // altitude, so up close it is a point of light, not a second sun.
  const curve = shot.easeIn ? Easing.bezier(0.32, 0, 0.67, 0) : Easing.bezier(0.45, 0, 0.35, 1);
  const altitude = interpolate(curve(zoomProgress), [0, 1], [shot.startDistance, shot.endDistance]) - EARTH_RADIUS;
  const pinScale = Math.max(0.05, altitude / (shot.startDistance - EARTH_RADIUS));

  // Pin pulses continuously during the hold, then settles once the zoom
  // commits so it doesn't distract up close.
  const pulseCycle = (frame / fps) % 1.4;
  const rawPulse = pulseCycle < 0.7 ? pulseCycle / 0.7 : 1 - (pulseCycle - 0.7) / 0.7;
  const pinPulse = interpolate(zoomProgress, [0, 0.15], [rawPulse, 0], { extrapolateRight: "clamp" });

  return (
    <ThreeCanvas width={width} height={height} style={{ backgroundColor: "#02040a" }}>
      <Stars />
      <Earth rotation={rotation} pinPulse={pinPulse} pinScale={pinScale} />
      <CameraRig progress={zoomProgress} rotation={rotation} shot={shot} />
    </ThreeCanvas>
  );
};
