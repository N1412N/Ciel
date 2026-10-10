/**
 * Thinking Orbs for Ciel Studio
 * Inspired by Jakub Antalik's thinking-orbs & libraries.dev
 * Pure 2D Canvas mathematical particle thought-orbs with 9 AI agent states.
 */

(function(global) {
  'use strict';

  function lerp(a, b, f) {
    return a + (b - a) * f;
  }
  function frac(x) {
    return x - Math.floor(x);
  }
  function hashD(a, b) {
    const h = Math.sin(a * 12.9898 + b * 78.233) * 43758.5453;
    return h - Math.floor(h);
  }
  function vnoise(x, y) {
    const xi = Math.floor(x);
    const yi = Math.floor(y);
    let fx = x - xi;
    let fy = y - yi;
    fx = fx * fx * (3 - 2 * fx);
    fy = fy * fy * (3 - 2 * fy);
    const a = hashD(xi, yi);
    const b = hashD(xi + 1, yi);
    const c = hashD(xi, yi + 1);
    const d = hashD(xi + 1, yi + 1);
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
  }
  function fibDir(i, n) {
    const golden = Math.PI * (3 - Math.sqrt(5));
    const y = 1 - 2 * (i + 0.5) / n;
    const rad = Math.sqrt(Math.max(0, 1 - y * y));
    const a = i * golden;
    return [rad * Math.cos(a), y, rad * Math.sin(a)];
  }
  function angleDelta(a, b) {
    return Math.atan2(Math.sin(a - b), Math.cos(a - b));
  }
  function makeProj(yaw, tilt, cx, cy, scale) {
    const st = Math.sin(tilt);
    const ct = Math.cos(tilt);
    const sy = Math.sin(yaw);
    const cyw = Math.cos(yaw);
    return function(x, y, z) {
      const x1 = x * cyw + z * sy;
      const z1 = -x * sy + z * cyw;
      const y1 = y * ct - z1 * st;
      const z2 = y * st + z1 * ct;
      return [cx + x1 * scale, cy - y1 * scale, z2];
    };
  }

  function inkColor(w, alpha, dark, tint) {
    if (!tint) {
      const g = Math.round((dark ? 1 - w : w) * 255);
      return `rgba(${g},${g},${g},${alpha})`;
    }
    const ramp = (c) => Math.round(dark ? c * (1 - w) : c + (255 - c) * w);
    return `rgba(${ramp(tint.r)},${ramp(tint.g)},${ramp(tint.b)},${alpha})`;
  }

  function paint(ctx, dots, dark, rMin = 0.3, tint) {
    for (let i = 0; i < dots.length; i++) {
      const d = dots[i];
      const alpha = d.a ?? 1;
      const w = Math.min(1, Math.max(0, d.white));
      ctx.fillStyle = inkColor(w, alpha, dark, tint);
      ctx.beginPath();
      ctx.arc(d.x, d.y, Math.max(rMin, d.r), 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function paintLines(ctx, lines, dark, tint) {
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      const alpha = l.a ?? 1;
      const w = Math.min(1, Math.max(0, l.white));
      ctx.strokeStyle = inkColor(w, alpha, dark, tint);
      ctx.lineWidth = l.w || 1;
      ctx.beginPath();
      ctx.moveTo(l.x1, l.y1);
      ctx.lineTo(l.x2, l.y2);
      ctx.stroke();
    }
  }

  function finalizeFrame(dots, lines, rMin = 0.3) {
    const visible = [];
    for (let i = 0; i < dots.length; i++) {
      const d = dots[i];
      if ((d.a ?? 1) < 0.02) continue;
      d.r = Math.max(rMin, d.r);
      visible.push(d);
    }
    visible.sort((a, b) => a.z - b.z);
    return { dots: visible, lines: lines.filter(l => (l.a ?? 1) >= 0.02) };
  }

  function radiusScale(size, pow) {
    return Math.pow(size / 300, pow);
  }

  // Preset scaling
  const COUNT_PAIRS = [["latRings", "lonDensity"], ["rings", "lonDensity"], ["lanes", "segs"]];
  const COUNT_KEYS = ["orbitN", "ghostN", "nodeN", "strandN", "signals"];
  const RADIUS_KEYS = ["rBase", "rDepth", "rActive", "rDot", "ghostR", "partR", "partRDepth", "nodeR", "nodeRDepth"];

  function scaleCounts(opts, scale) {
    const out = Object.assign({}, opts);
    const done = new Set();
    const rt = Math.sqrt(scale);
    for (let pair of COUNT_PAIRS) {
      const a = pair[0], b = pair[1];
      const va = out[a], vb = out[b];
      if (va != null && vb != null && !done.has(a) && !done.has(b)) {
        out[a] = Math.max(2, Math.round(va * rt));
        out[b] = Math.max(2, Math.round(vb * rt));
        done.add(a);
        done.add(b);
      }
    }
    for (let k of COUNT_KEYS) {
      const v = out[k];
      if (v != null && v !== 0 && !done.has(k)) out[k] = Math.max(1, Math.round(v * scale));
    }
    return out;
  }

  function scaleRadii(opts, scale) {
    const out = Object.assign({}, opts);
    for (let k of RADIUS_KEYS) {
      const v = out[k];
      if (v != null) out[k] = v * scale;
    }
    return out;
  }

  const BASE_PROFILES = {
    globe: { latRings: 17, lonDensity: 44, rBase: 0.6, rDepth: 1.7, rBoost: 1, inkFar: 0.62, inkSpan: 0.54, rsPow: 0.6, rMin: 0.3 },
    orbits: { orbitN: 12, ghostN: 40, ghostR: 0.9, ghostA: 0.5, particles: 3, partR: 1.2, partRDepth: 1.6, rsPow: 0.6, rMin: 0.3 },
    rubik: { latRings: 15, lonDensity: 40, moveCount: 14, rBase: 0.6, rDepth: 1.7, rActive: 0.3, inkFar: 0.62, inkSpan: 0.54, rsPow: 0.6, rMin: 0.3 },
    wave: { rings: 15, lonDensity: 40, rBase: 0.6, rDepth: 1.7, rsPow: 0.6, rMin: 0.3 },
    web: { nodeN: 30, thr: 0.72, signals: 5, nodeR: 1.4, nodeRDepth: 1.8, lineW: 0.8, rsPow: 0.6, rMin: 0.3 },
    braid: { strandN: 52, turns: 3, ghostN: 150, rBase: 1.2, rDepth: 1.8, rsPow: 0.6, rMin: 0.3 },
    ribbon: { lanes: 5, segs: 88, ghostN: 150, rBase: 1.1, rDepth: 1.7, rsPow: 0.6, rMin: 0.3 },
    ring: { lanes: 5, segs: 88, ghostN: 0, faceOn: 1, rBase: 1.1, rDepth: 1.7, rsPow: 0.6, rMin: 0.3 },
    morph: { rDot: 0.021, iconD: 1, rMin: 0.25 }
  };

  // --- Frame Generators ---
  function frameOrbits(size, t, o) {
    const cx = size / 2, cy = size / 2, R = size / 2 * 0.82;
    const pt = makeProj(t * 0.12, 0.3, cx, cy, 1);
    const rs = radiusScale(size, o.rsPow ?? 0.6);
    const dots = [];
    const orbitN = o.orbitN ?? 12, ghostN = o.ghostN ?? 40, particles = o.particles ?? 3;
    for (let orb = 0; orb < orbitN; orb++) {
      const h1 = hashD(orb, 1.7), h2 = hashD(orb, 5.2), h3 = hashD(orb, 8.9);
      const ro = R * (0.45 + 0.52 * h1);
      const th = h1 * 2 * Math.PI, phi = Math.acos(2 * h2 - 1);
      const nx = Math.sin(phi) * Math.cos(th), ny = Math.cos(phi), nz = Math.sin(phi) * Math.sin(th);
      let ux = -ny, uy = nx, uz = 0;
      const ul = Math.max(1e-6, Math.sqrt(ux * ux + uy * uy));
      ux /= ul; uy /= ul;
      const vx = ny * uz - nz * uy, vy = nz * ux - nx * uz, vz = nx * uy - ny * ux;
      const speed = (0.25 + 0.55 * h3) * (h3 > 0.5 ? 1 : -1);
      for (let k = 0; k < ghostN; k++) {
        const a = k / ghostN * 2 * Math.PI;
        const [px, py, z] = pt((ux * Math.cos(a) + vx * Math.sin(a)) * ro, (uy * Math.cos(a) + vy * Math.sin(a)) * ro, (uz * Math.cos(a) + vz * Math.sin(a)) * ro);
        const depth = (z / ro + 1) / 2;
        dots.push({ x: px, y: py, z, r: (o.ghostR ?? 0.9) * rs, white: 0.72, a: (o.ghostA ?? 0.5) * (0.4 + 0.6 * depth) });
      }
      for (let m = 0; m < particles; m++) {
        const a = t * speed + m / particles * 2 * Math.PI + h2 * 6;
        const [px, py, z] = pt((ux * Math.cos(a) + vx * Math.sin(a)) * ro, (uy * Math.cos(a) + vy * Math.sin(a)) * ro, (uz * Math.cos(a) + vz * Math.sin(a)) * ro);
        const depth = (z / ro + 1) / 2;
        dots.push({ x: px, y: py, z, r: ((o.partR ?? 1.2) + (o.partRDepth ?? 1.6) * depth) * rs, white: 0.3 - 0.22 * depth, a: 1 });
      }
    }
    return finalizeFrame(dots, [], o.rMin);
  }

  function frameGlobe(size, t, o) {
    const spin = 0.5, cx = size / 2, cy = size / 2, radius = size / 2 * 0.82;
    const tilt = 0.4 + 0.06 * Math.sin(t * 0.35);
    const pt = makeProj(t * spin, tilt, cx, cy, radius);
    const scan = t * (spin + (1.7 - spin) * (o.scanMul ?? 1));
    const rs = radiusScale(size, o.rsPow ?? 0.6);
    const dimBase = o.dimBase ?? 1;
    const dots = [];
    const latRings = o.latRings ?? 17, lonDensity = o.lonDensity ?? 44;
    for (let li = 0; li <= latRings; li++) {
      const lat = -Math.PI / 2 + li / latRings * Math.PI;
      const cosLat = Math.cos(lat), sinLat = Math.sin(lat);
      const lonCount = Math.max(1, Math.round(Math.abs(cosLat) * lonDensity));
      for (let lj = 0; lj < lonCount; lj++) {
        const lon = lj / lonCount * 2 * Math.PI;
        const [px, py, z] = pt(cosLat * Math.cos(lon), sinLat, cosLat * Math.sin(lon));
        const depth = (z + 1) / 2;
        const d = angleDelta(lon + t * spin, scan);
        const boost = Math.exp(-(d * d) / 0.18) * Math.max(0, z);
        dots.push({
          x: px, y: py, z,
          r: ((o.rBase ?? 0.6) + (o.rDepth ?? 1.7) * depth + (o.rBoost ?? 1) * boost) * rs,
          white: (o.inkFar ?? 0.62) - (o.inkSpan ?? 0.54) * depth,
          a: dimBase + (1 - dimBase) * Math.min(1, boost)
        });
      }
    }
    return finalizeFrame(dots, [], o.rMin);
  }

  function frameWave(size, t, o) {
    const cx = size / 2, cy = size / 2, R = size / 2 * 0.874;
    const pt = makeProj(t * 0.18, 0.38, cx, cy, 1);
    const rs = radiusScale(size, o.rsPow ?? 0.6);
    const dots = [];
    const rings = o.rings ?? 15, lonDensity = o.lonDensity ?? 40;
    for (let ri = 0; ri <= rings; ri++) {
      const lat = -Math.PI / 2 + ri / rings * Math.PI;
      const cosLat = Math.cos(lat), sinLat = Math.sin(lat);
      const w = 0.62 * Math.sin(t * 2.1 - ri * 0.52) + 0.38 * Math.sin(t * 1.27 + ri * 0.83);
      const rr = R * (0.88 + 0.105 * w);
      const lonCount = Math.max(1, Math.round(Math.abs(cosLat) * lonDensity));
      for (let lj = 0; lj < lonCount; lj++) {
        const lon = lj / lonCount * 2 * Math.PI;
        const [px, py, z] = pt(cosLat * Math.cos(lon) * rr, sinLat * rr, cosLat * Math.sin(lon) * rr);
        const depth = (z / R + 1) / 2;
        const crest = Math.max(0, w);
        dots.push({
          x: px, y: py, z,
          r: ((o.rBase ?? 0.6) + (o.rDepth ?? 1.7) * depth) * (1 + 0.4 * crest) * rs,
          white: 0.66 - 0.56 * depth - 0.1 * crest,
          a: 0.35 + 0.65 * depth
        });
      }
    }
    return finalizeFrame(dots, [], o.rMin);
  }

  function frameBraid(size, t, o) {
    const cx = size / 2, cy = size / 2, R = size / 2 * 0.76;
    const pt = makeProj(t * 0.4, 0.3, cx, cy, 1);
    const rs = radiusScale(size, o.rsPow ?? 0.6);
    const dots = [];
    const ghostN = o.ghostN ?? 150;
    for (let i = 0; i < ghostN; i++) {
      const d = fibDir(i, ghostN);
      const [px, py, z] = pt(d[0] * R, d[1] * R, d[2] * R);
      const depth = (z / R + 1) / 2;
      dots.push({ x: px, y: py, z, r: 0.8 * rs, white: 0.78, a: 0.1 + 0.22 * depth });
    }
    const strandN = o.strandN ?? 52, turns = o.turns ?? 3;
    for (let s = 0; s < 3; s++) {
      const phase = s / 3 * 2 * Math.PI;
      for (let i = 0; i < strandN; i++) {
        const u = (frac(i / strandN + t * 0.045) * 2 - 1) * 0.96;
        const surf = Math.sqrt(Math.max(0, 1 - u * u));
        const endFade = Math.min(1, (1 - Math.abs(u)) / 0.1);
        const a = u * Math.PI * turns + phase;
        const weave = 1 + 0.075 * Math.sin(u * Math.PI * turns * 2 + phase * 2 + t * 0.8);
        const rr = surf * R * weave;
        const [px, py, zr] = pt(Math.cos(a) * rr, u * R * weave, Math.sin(a) * rr);
        const depth = (zr / R + 1) / 2;
        dots.push({
          x: px, y: py, z: zr,
          r: ((o.rBase ?? 1.2) + (o.rDepth ?? 1.8) * depth) * rs,
          white: 0.55 - 0.45 * depth,
          a: endFade * (0.45 + 0.55 * depth)
        });
      }
    }
    return finalizeFrame(dots, [], o.rMin);
  }

  function frameRibbon(size, t, o) {
    const cx = size / 2, cy = size / 2, R = size / 2 * 0.78;
    const spin = o.spin ?? 1, camTilt = 0.3;
    const pt = makeProj(t * 0.1 * spin, camTilt, cx, cy, 1);
    const rs = radiusScale(size, o.rsPow ?? 0.6);
    const dots = [];
    const ghostN = o.ghostN ?? 150;
    for (let i = 0; i < ghostN; i++) {
      const d = fibDir(i, ghostN);
      const [px, py, z] = pt(d[0] * R, d[1] * R, d[2] * R);
      const depth = (z / R + 1) / 2;
      dots.push({ x: px, y: py, z, r: 0.8 * rs, white: 0.78, a: 0.1 + 0.22 * depth });
    }
    const ya = t * 0.24 * spin;
    const ta = o.faceOn ? -camTilt : 0.55 + 0.3 * Math.sin(t * 0.18) * spin;
    const ux = Math.cos(ya), uy = 0, uz = Math.sin(ya);
    const vx = -uz * Math.sin(ta), vy = Math.cos(ta), vz = ux * Math.sin(ta);
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const wobAmp = 0.23 * (o.wobMul ?? 1);
    const baseR = o.faceOn ? R / (1 + 0.85 * wobAmp) : R;
    const baseLanes = o.lanes ?? 5, segs = o.segs ?? 88;
    const lanes = Math.max(1, Math.round(baseLanes * (o.bandMul ?? 1)));
    for (let w = 0; w < lanes; w++) {
      const laneOff = (w - (lanes - 1) / 2) * 0.075;
      const edge = Math.abs(w - (lanes - 1) / 2) / Math.max(1, (lanes - 1) / 2);
      for (let k = 0; k < segs; k++) {
        const a = k / segs * 2 * Math.PI;
        const wob = (0.16 * Math.sin(a * 3 - t * 1.7 + w * 0.22) + 0.07 * Math.sin(a * 5 + t * 1.1)) * (o.wobMul ?? 1);
        const radial = o.faceOn ? 1 + wob : 1;
        const off = o.faceOn ? laneOff : laneOff + wob;
        const x = ux * Math.cos(a) + vx * Math.sin(a) + nx * off;
        const y = uy * Math.cos(a) + vy * Math.sin(a) + ny * off;
        const z = uz * Math.cos(a) + vz * Math.sin(a) + nz * off;
        const l = Math.sqrt(x * x + y * y + z * z);
        const rr = baseR * radial;
        const [px, py, zr] = pt(x / l * rr, y / l * rr, z / l * rr);
        const depth = (zr / R + 1) / 2;
        dots.push({
          x: px, y: py, z: zr,
          r: ((o.rBase ?? 1.1) + (o.rDepth ?? 1.7) * depth) * (1 - 0.25 * edge) * rs,
          white: 0.52 - 0.44 * depth + 0.18 * edge,
          a: 0.4 + 0.6 * depth
        });
      }
    }
    return finalizeFrame(dots, [], o.rMin);
  }

  function frameWeb(size, t, o) {
    const cx = size / 2, cy = size / 2, R = size / 2 * 0.8 * (o.spread ?? 1);
    const pt = makeProj(t * 0.12, 0.32, cx, cy, R);
    const rs = radiusScale(size, o.rsPow ?? 0.6);
    const nodeN = o.nodeN ?? 30, thr = o.thr ?? 0.72;
    const nodeR = o.nodeR ?? 1.4, nodeRDepth = o.nodeRDepth ?? 1.8;
    const nodes = [];
    for (let i = 0; i < nodeN; i++) {
      const d = fibDir(i, nodeN);
      const x = d[0] + 0.3 * (vnoise(i * 0.31 + 9, t * 0.24) - 0.5) * 2;
      const y = d[1] + 0.3 * (vnoise(i * 0.53 + 27, t * 0.21) - 0.5) * 2;
      const z = d[2] + 0.3 * (vnoise(i * 0.77 + 55, t * 0.27) - 0.5) * 2;
      const l = Math.sqrt(x * x + y * y + z * z);
      nodes.push([x / l, y / l, z / l]);
    }
    const lines = [], dots = [];
    for (let i = 0; i < nodeN; i++) {
      for (let j = i + 1; j < nodeN; j++) {
        const dx = nodes[i][0] - nodes[j][0], dy = nodes[i][1] - nodes[j][1], dz = nodes[i][2] - nodes[j][2];
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (dist >= thr) continue;
        const [x1, y1, z1] = pt(nodes[i][0], nodes[i][1], nodes[i][2]);
        const [x2, y2, z2] = pt(nodes[j][0], nodes[j][1], nodes[j][2]);
        const depth = ((z1 + z2) / 2 + 1) / 2;
        lines.push({ x1, y1, x2, y2, white: 0.42, a: (1 - dist / thr) * (0.3 + 0.55 * depth), w: Math.max(0.6, (o.lineW ?? 0.8) * rs) });
      }
    }
    for (let i = 0; i < nodeN; i++) {
      const [px, py, z] = pt(nodes[i][0], nodes[i][1], nodes[i][2]);
      const depth = (z + 1) / 2;
      const pulse = 1 + 0.25 * Math.sin(t * 1.4 + i * 2.7);
      dots.push({ x: px, y: py, z, r: (nodeR + nodeRDepth * depth) * pulse * rs, white: 0.55 - 0.45 * depth, a: 0.9 });
    }
    return finalizeFrame(dots, lines, o.rMin);
  }

  function frameMorph(size, t, o) {
    const cx = size / 2, cy = size / 2;
    const pts = [];
    const steps = 36;
    const aCycle = (t * 0.5) % 3;
    const stage = Math.floor(aCycle);
    const prog = frac(aCycle);
    const morphP = prog * prog * (3 - 2 * prog);

    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * Math.PI * 2;
      // Shape 0: Circle
      const rCircle = size * 0.32;
      const x0 = Math.cos(angle) * rCircle, y0 = Math.sin(angle) * rCircle;

      // Shape 1: Triangle
      const aTri = angle + Math.PI / 2;
      const side = 3;
      const rTri = size * 0.34 / Math.cos((aTri % (2 * Math.PI / side)) - Math.PI / side);
      const x1 = Math.cos(angle) * Math.min(rTri, size * 0.38), y1 = Math.sin(angle) * Math.min(rTri, size * 0.38);

      // Shape 2: Diamond / Square
      const aSq = angle + Math.PI / 4;
      const rSq = size * 0.28 / Math.max(Math.abs(Math.cos(aSq)), Math.abs(Math.sin(aSq)));
      const x2 = Math.cos(angle) * Math.min(rSq, size * 0.38), y2 = Math.sin(angle) * Math.min(rSq, size * 0.38);

      let x, y;
      if (stage === 0) {
        x = lerp(x0, x1, morphP); y = lerp(y0, y1, morphP);
      } else if (stage === 1) {
        x = lerp(x1, x2, morphP); y = lerp(y1, y2, morphP);
      } else {
        x = lerp(x2, x0, morphP); y = lerp(y2, y0, morphP);
      }

      pts.push({
        x: cx + x,
        y: cy + y,
        z: 0,
        r: 1.6,
        white: 0.1,
        a: 0.95
      });
    }
    return finalizeFrame(pts, [], 0.3);
  }

  const MODE_FRAMES = {
    orbits: frameOrbits,
    globe: frameGlobe,
    rubik: frameGlobe,
    wave: frameWave,
    web: frameWeb,
    braid: frameBraid,
    ribbon: frameRibbon,
    ring: frameRibbon,
    morph: frameMorph
  };

  const STATE_TO_MODE = {
    working: 'orbits',
    orbits: 'orbits',
    searching: 'globe',
    globe: 'globe',
    solving: 'rubik',
    rubik: 'rubik',
    listening: 'wave',
    wave: 'wave',
    connecting: 'web',
    web: 'web',
    weaving: 'braid',
    braid: 'braid',
    composing: 'ribbon',
    ribbon: 'ribbon',
    breathing: 'ring',
    ring: 'ring',
    shaping: 'morph',
    morph: 'morph',
    idle: 'ring',
    thinking: 'ribbon',
    active: 'orbits'
  };

  const THINKING_ORB_STATES = [
    { id: 'breathing', mode: 'ring', label: 'Breathing', icon: 'fa-wind', tint: { r: 56, g: 189, b: 248 }, desc: 'Idle cosmic harmonic resonance' },
    { id: 'listening', mode: 'wave', label: 'Listening', icon: 'fa-wave-square', tint: { r: 52, g: 211, b: 153 }, desc: 'Acoustic waveform voice sensing' },
    { id: 'composing', mode: 'ribbon', label: 'Composing', icon: 'fa-pen-nib', tint: { r: 14, g: 165, b: 233 }, desc: 'Multi-band generative thought ribbon' },
    { id: 'searching', mode: 'globe', label: 'Searching', icon: 'fa-globe', tint: { r: 251, g: 191, b: 36 }, desc: 'Spherical meridian knowledge sweep' },
    { id: 'solving', mode: 'rubik', label: 'Solving', icon: 'fa-cube', tint: { r: 168, g: 85, b: 247 }, desc: 'Permutative algorithmic solution' },
    { id: 'shaping', mode: 'morph', label: 'Shaping', icon: 'fa-shapes', tint: { r: 244, g: 63, b: 94 }, desc: 'Geometric morphing art creation' },
    { id: 'working', mode: 'orbits', label: 'Working', icon: 'fa-atom', tint: { r: 99, g: 102, b: 241 }, desc: 'Multi-planar orbital agent execution' },
    { id: 'connecting', mode: 'web', label: 'Connecting', icon: 'fa-network-wired', tint: { r: 20, g: 184, b: 166 }, desc: 'Constellation graph associative memory' },
    { id: 'weaving', mode: 'braid', label: 'Weaving', icon: 'fa-dna', tint: { r: 59, g: 130, b: 246 }, desc: 'Triple-helical logic synthesis' }
  ];

  const PRESETS = {
    orbits: { 64: { speed: 1.88, count: 1, size: 1 }, 44: { speed: 2.2, count: 0.7, size: 1.3 }, 20: { speed: 3.9, count: 0.24, size: 2.4 } },
    globe: { 64: { speed: 2.01, count: 0.42, size: 1.15, extra: { scanMul: 4.08, dimBase: 0.45 } }, 44: { speed: 2.2, count: 0.28, size: 1.35, extra: { scanMul: 4.15, dimBase: 0.45 } }, 20: { speed: 2.66, count: 0.1, size: 1.75, extra: { scanMul: 4.33, dimBase: 0.45 } } },
    rubik: { 64: { speed: 1.82, count: 0.35, size: 1.05 }, 44: { speed: 1.85, count: 0.22, size: 1.25 }, 20: { speed: 1.95, count: 0.09, size: 1.9 } },
    wave: { 64: { speed: 4.38, count: 0.34, size: 1 }, 44: { speed: 4.2, count: 0.22, size: 1.2 }, 20: { speed: 4.0, count: 0.1, size: 1.6 } },
    web: { 64: { speed: 3.31, count: 1.35, size: 0.95 }, 44: { speed: 4.2, count: 0.8, size: 1.15 }, 20: { speed: 6.63, count: 0.25, size: 1.52 } },
    braid: { 64: { speed: 1.62, count: 0.5, size: 1 }, 44: { speed: 2.0, count: 0.3, size: 1.15 }, 20: { speed: 2.75, count: 0.11, size: 1.36 } },
    ribbon: { 64: { speed: 2.34, count: 0.25, size: 0.85, extra: { spin: 0, bandMul: 3.9, wobMul: 1 } }, 44: { speed: 2.6, count: 0.15, size: 0.95, extra: { spin: 0, bandMul: 4.2, wobMul: 1 } }, 20: { speed: 3.12, count: 0.05, size: 1.07, extra: { spin: 0, bandMul: 4.9, wobMul: 1 } } },
    ring: { 64: { speed: 3.24, count: 0.25, size: 0.95, extra: { spin: 0, bandMul: 3.6, wobMul: 0.37 } }, 44: { speed: 3.4, count: 0.12, size: 1.15, extra: { spin: 0, bandMul: 3.7, wobMul: 0.42 } }, 20: { speed: 3.78, count: 0.03, size: 1.62, extra: { spin: 0, bandMul: 3.9, wobMul: 0.56 } } },
    morph: { 64: { speed: 2.4, count: 0.7, size: 0.4, extra: { spread: 1.45 } }, 44: { speed: 2.3, count: 0.65, size: 0.6, extra: { spread: 1.45 } }, 20: { speed: 2.08, count: 0.53, size: 1.0, extra: { spread: 1.45 } } }
  };

  function resolvePreset(state, size) {
    const mode = STATE_TO_MODE[state] || 'ring';
    const presetMap = PRESETS[mode] || PRESETS.ring;
    const targetSize = size <= 28 ? 20 : size <= 52 ? 44 : 64;
    const preset = presetMap[targetSize] || presetMap[64];
    let opts = Object.assign({}, BASE_PROFILES[mode]);
    if (preset.count !== 1) opts = scaleCounts(opts, preset.count);
    if (preset.size !== 1) opts = scaleRadii(opts, preset.size);
    if (preset.extra) Object.assign(opts, preset.extra);
    return { mode, speed: preset.speed, opts };
  }

  // --- ThinkingOrb Controller Class ---
  class ThinkingOrb {
    constructor(canvas, options = {}) {
      this.canvas = typeof canvas === 'string' ? document.getElementById(canvas) : canvas;
      if (!this.canvas) return;
      this.ctx = this.canvas.getContext('2d');
      this.size = options.size || this.canvas.width || 44;
      this.state = options.state || 'breathing';
      this.dark = options.dark !== undefined ? options.dark : true;
      // Ciel default luminous cyan tint: { r: 56, g: 189, b: 248 }
      this.tint = options.tint || { r: 56, g: 189, b: 248 };
      this.time = 0;
      this.animId = null;
      this.lastTimestamp = null;
      this.isRunning = false;

      this.initCanvas();
      this.start();
    }

    initCanvas() {
      const dpr = window.devicePixelRatio || 1;
      this.canvas.width = this.size * dpr;
      this.canvas.height = this.size * dpr;
      this.canvas.style.width = this.size + 'px';
      this.canvas.style.height = this.size + 'px';
      this.ctx.scale(dpr, dpr);
    }

    setState(newState) {
      if (this.state === newState) return;
      this.state = newState;
    }

    getStateInfo() {
      const mode = STATE_TO_MODE[this.state] || 'ring';
      return THINKING_ORB_STATES.find(s => s.id === this.state || s.mode === mode) || {
        id: this.state,
        mode: mode,
        label: this.state.charAt(0).toUpperCase() + this.state.slice(1),
        icon: 'fa-circle-notch',
        tint: this.tint,
        desc: 'Autonomous AI Core'
      };
    }

    setTint(rgb) {
      this.tint = rgb;
    }

    setDark(isDark) {
      this.dark = isDark;
    }

    render(t) {
      const { mode, speed, opts } = resolvePreset(this.state, this.size);
      const frameFn = MODE_FRAMES[mode] || frameRibbon;
      const frame = frameFn(this.size, t * (speed || 1), opts);

      this.ctx.clearRect(0, 0, this.size, this.size);

      // Render lines first if any
      if (frame.lines && frame.lines.length) {
        paintLines(this.ctx, frame.lines, this.dark, this.tint);
      }
      // Render dots
      paint(this.ctx, frame.dots, this.dark, 0.3, this.tint);
    }

    start() {
      if (this.isRunning) return;
      this.isRunning = true;
      const loop = (timestamp) => {
        if (!this.isRunning) return;
        if (!this.lastTimestamp) this.lastTimestamp = timestamp;
        const dt = (timestamp - this.lastTimestamp) / 1000;
        this.lastTimestamp = timestamp;

        // Cap dt to prevent huge jumps
        this.time += Math.min(dt, 0.1);
        this.render(this.time);
        this.animId = requestAnimationFrame(loop);
      };
      this.animId = requestAnimationFrame(loop);
    }

    stop() {
      this.isRunning = false;
      if (this.animId) {
        cancelAnimationFrame(this.animId);
        this.animId = null;
      }
    }

    destroy() {
      this.stop();
      if (this.canvas) {
        this.ctx.clearRect(0, 0, this.size, this.size);
      }
    }
  }

  // Export to global scope
  global.ThinkingOrb = ThinkingOrb;
  global.THINKING_ORB_STATES = THINKING_ORB_STATES;
  global.STATE_TO_MODE = STATE_TO_MODE;
  global.createThinkingOrb = function(canvas, options) {
    return new ThinkingOrb(canvas, options);
  };

})(typeof window !== 'undefined' ? window : this);
