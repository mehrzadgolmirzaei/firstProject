/* =====================================================================
   نمای سه‌بعدی فونداسیون — Three.js
   مدل از همان اعدادی ساخته می‌شود که موتور محاسبه بیرون داده:
   بتن مگر، پی، ستون، شبکه آرماتور، خاموت و میل مهار.
   این تنها جای صفحه است که حرکت دارد، و حرکتش پاسخ به عمل کاربر است.
   ===================================================================== */
(function (global) {
  "use strict";

  // همان پالت ملایم فایل سه‌بعدی اتوکد (model3d.py)
  const C = {
    lean:   0x807C74,
    pad:    0xD4D0C8,
    pedestal: 0xD4D0C8,
    rebar:  0x7E5440,   // قهوه‌ای زنگ‌زده مات
    tie:    0x96705A,
    anchor: 0xB0B6BC,   // فولاد گالوانیزه
    plate:  0x969EA6,
    grout:  0xC6BEAC,
    ground: 0x2A333B,
    chord:  0x8A959E,   // سازه فولادی گالوانیزه
    brace:  0xA9B3BA,
    strut:  0x9AA4AC,
    beam:   0x6E7B86,
    porcelain: 0x7A543E,  // مقره چینی
    tank:   0xA8B0B6,
    metal:  0xBEC4C8,
    terminal: 0xC49650,
  };

  /** تجهیز روی سازه: استوانه و منشور (structural/equipment3d) */
  function equipmentGroup(prims, k) {
    const g = new THREE.Group();
    const mats = {};
    const mat = (name) => mats[name] || (mats[name] = new THREE.MeshStandardMaterial({
      color: C[name] || C.metal, roughness: name === "porcelain" ? 0.35 : 0.5,
      metalness: name === "porcelain" ? 0.05 : 0.4 }));
    const P3 = (v) => new THREE.Vector3(v[0] * k, v[2] * k, -v[1] * k);
    prims.forEach((pr) => {
      const a = P3(pr.p), b = P3(pr.q);
      const dir = new THREE.Vector3().subVectors(b, a);
      const len = Math.max(dir.length(), 1e-4);
      if (pr.t === "cyl") {
        const m = new THREE.Mesh(new THREE.CylinderGeometry(pr.r * k, pr.r * k, len, 20), mat(pr.g));
        m.position.copy(a).add(b).multiplyScalar(0.5);
        m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize());
        g.add(m);
      } else {
        const [[u0, v0], , [u1, v1]] = pr.profile[0];
        const e2 = P3([pr.e2[0], pr.e2[1], pr.e2[2]].map((x) => x / k)).normalize();
        const e3 = P3([pr.e3[0], pr.e3[1], pr.e3[2]].map((x) => x / k)).normalize();
        const box = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), mat(pr.g));
        const e1 = dir.clone().normalize();
        box.matrixAutoUpdate = false;
        const centre = a.clone().add(b).multiplyScalar(0.5);
        box.matrix.makeBasis(e1.multiplyScalar(len), e2.multiplyScalar((u1 - u0) * k),
                             e3.multiplyScalar((v1 - v0) * k)).setPosition(centre);
        g.add(box);
      }
    });
    g.userData.steel = true;
    return g;
  }

  /** رنگ نسبت تنش: سبز ← زرد ← نارنجی ← قرمز (همان structural/placement.ratio_color) */
  function ratioColor(r) {
    const t = Math.max(0, Math.min(1.2, r)) / 1.2;
    const stops = [[0, [46, 125, 80]], [0.55, [214, 170, 40]], [0.83, [214, 90, 40]], [1, [170, 30, 30]]];
    for (let i = 0; i + 1 < stops.length; i++) {
      const [t0, c0] = stops[i], [t1, c1] = stops[i + 1];
      if (t <= t1) {
        const k = (t - t0) / (t1 - t0);
        return new THREE.Color(...c0.map((v, j) => (v + (c1[j] - v) * k) / 255));
      }
    }
    return new THREE.Color(170 / 255, 30 / 255, 30 / 255);
  }

  /** اعضای سازه با مقطع واقعی — یک هندسه با رنگ هر رأس (گروه یا نسبت تنش) */
  function steelMesh(members, k, heat) {
    const pos = [], col = [];
    const P3 = (v) => [v[0] * k, v[2] * k, -v[1] * k];
    const at = (o, e2, e3, u, w) => [o[0] + u * e2[0] + w * e3[0],
      o[1] + u * e2[1] + w * e3[1], o[2] + u * e2[2] + w * e3[2]];
    members.forEach((mb) => {
      const c = heat ? ratioColor(mb.ratio) : new THREE.Color(C[mb.group] || C.brace);
      const push = (...pts) => pts.forEach((p) => { pos.push(...p); col.push(c.r, c.g, c.b); });
      mb.profile.forEach((poly) => {
        const a = poly.map(([u, w]) => P3(at(mb.p, mb.e2, mb.e3, u, w)));
        const b = poly.map(([u, w]) => P3(at(mb.q, mb.e2, mb.e3, u, w)));
        const n = poly.length;
        for (let i = 0; i < n; i++) {
          const j = (i + 1) % n;
          push(a[i], a[j], b[j], a[i], b[j], b[i]);
        }
        THREE.ShapeUtils.triangulateShape(poly.map(([u, w]) => new THREE.Vector2(u, w)), [])
          .forEach(([i, j, l]) => { push(a[i], a[j], a[l]); push(b[i], b[l], b[j]); });
      });
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    g.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.5,
      metalness: heat ? 0.05 : 0.35, side: THREE.DoubleSide, flatShading: true });
    mat.userData.opacity = 1;
    const mesh = new THREE.Mesh(g, mat);
    mesh.userData.steel = true;
    return mesh;
  }

  function Viewer(container) {
    this.el = container;
    this.ready = typeof THREE !== "undefined";
    if (!this.ready) return;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x1F272F);
    this.scene.fog = new THREE.Fog(0x1F272F, 10, 26);

    this.camera = new THREE.PerspectiveCamera(38, 4 / 3, 0.1, 200);
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.el.appendChild(this.renderer.domElement);

    this.scene.add(new THREE.HemisphereLight(0xBFD3E0, 0x1A242E, 0.85));
    const key = new THREE.DirectionalLight(0xFFF4E8, 0.95);
    key.position.set(4, 7, 5);
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0x8FB8D8, 0.4);
    rim.position.set(-5, 3, -4);
    this.scene.add(rim);

    this.group = new THREE.Group();
    this.scene.add(this.group);

    this.theta = -0.7; this.phi = 1.03; this.dist = 7.5;
    this.autoRotate = true;
    this._bindInput();
    this._resize();
    addEventListener("resize", () => this._resize());
    this._loop();
  }

  Viewer.prototype._bindInput = function () {
    const el = this.renderer.domElement;
    let dragging = false, lx = 0, ly = 0;
    el.style.cursor = "grab";
    el.addEventListener("pointerdown", (e) => {
      dragging = true; lx = e.clientX; ly = e.clientY;
      this.autoRotate = false; el.style.cursor = "grabbing";
      el.setPointerCapture(e.pointerId);
    });
    el.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      this.theta -= (e.clientX - lx) * 0.006;
      this.phi = Math.max(0.15, Math.min(1.45, this.phi - (e.clientY - ly) * 0.005));
      lx = e.clientX; ly = e.clientY;
    });
    const stop = (e) => { dragging = false; el.style.cursor = "grab"; };
    el.addEventListener("pointerup", stop);
    el.addEventListener("pointercancel", stop);
    el.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.dist = Math.max(3, Math.min(20, this.dist + Math.sign(e.deltaY) * 0.5));
    }, { passive: false });
  };

  Viewer.prototype._resize = function () {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
  };

  Viewer.prototype._loop = function () {
    requestAnimationFrame(() => this._loop());
    if (this.autoRotate) this.theta += 0.0022;
    const r = this.dist;
    this.camera.position.set(
      r * Math.sin(this.phi) * Math.cos(this.theta),
      r * Math.cos(this.phi),
      r * Math.sin(this.phi) * Math.sin(this.theta));
    this.camera.lookAt(0, 0.35, 0);
    if (this.build0 !== undefined && this.build0 < 1) {
      this.build0 = Math.min(1, this.build0 + 0.035);
      this.group.scale.y = 0.25 + 0.75 * this._ease(this.build0);
      this.group.traverse((o) => {
        // شفافیت نهایی هر ماده حفظ می‌شود؛ انیمیشن فقط از صفر به همان مقدار می‌رود
        if (o.material && o.material.transparent) {
          o.material.opacity = this.build0 * (o.material.userData.opacity ?? 1);
        }
      });
    }
    this.renderer.render(this.scene, this.camera);
  };

  Viewer.prototype._ease = function (t) { return 1 - Math.pow(1 - t, 3); };

  Viewer.prototype._clear = function () {
    while (this.group.children.length) {
      const o = this.group.children.pop();
      o.traverse && o.traverse((c) => {
        if (c.geometry) c.geometry.dispose();
        if (c.material) c.material.dispose();
      });
    }
  };

  function box(w, h, d, color, opacity) {
    const m = new THREE.MeshStandardMaterial({
      color, roughness: 0.85, metalness: 0.05,
      transparent: opacity !== undefined, opacity: opacity === undefined ? 1 : opacity,
      depthWrite: opacity === undefined,
    });
    m.userData.opacity = m.opacity;
    return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
  }

  /** میلگرد بین دو نقطه (مختصات three.js) */
  function segment(a, b, dia, color) {
    const dir = new THREE.Vector3().subVectors(b, a);
    const len = dir.length();
    const m = new THREE.MeshStandardMaterial({ color, roughness: 0.65, metalness: 0.2 });
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(dia / 2, dia / 2, len, 12), m);
    mesh.position.copy(a).add(b).multiplyScalar(0.5);
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize());
    return mesh;
  }

  // مختصات مدل: میلی‌متر، z رو به بالا ← three.js: متر، y رو به بالا
  const P = (p) => new THREE.Vector3(p[0] / 1000, p[2] / 1000, -p[1] / 1000);

  function edged(group, w, h, d, pos, color, opacity) {
    const b = box(w, h, d, color, opacity);
    b.position.copy(pos);
    group.add(b);
    const e = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w, h, d)),
      new THREE.LineBasicMaterial({ color: 0xD6DEE4 }));
    e.position.copy(pos);
    group.add(e);
  }

  /**
   * ساخت مدل از مدل مرکزی سرور (model.py) — همان مختصاتی که نقشه دوبعدی و
   * فایل سه‌بعدی اتوکد از آن ساخته می‌شوند.
   */
  Viewer.prototype.build = function (m) {
    if (!this.ready || !m) return;
    this._clear();
    const k = 1 / 1000;
    const L = m.L * k, B = m.B * k, tf = m.tf * k, lean = m.lean * k, lm = m.lean_margin * k;
    const top = m.top * k;

    const ground = new THREE.Mesh(new THREE.PlaneGeometry(L * 3.2, B * 3.2),
      new THREE.MeshStandardMaterial({ color: C.ground, roughness: 1 }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -lean - 0.001;
    this.group.add(ground);

    const lc = box(L + 2 * lm, lean, B + 2 * lm, C.lean);
    lc.position.y = -lean / 2;
    this.group.add(lc);
    edged(this.group, L, tf, B, new THREE.Vector3(0, tf / 2, 0), C.pad, 0.55);
    m.pedestals.forEach((p) => {
      const h = top - tf;
      edged(this.group, p.size * k, h, p.size * k,
        new THREE.Vector3(p.x * k, tf + h / 2, -p.y * k), C.pedestal, 0.45);
    });

    m.bars.forEach((bar) => {
      const pts = bar.points.map(P);
      if (bar.closed) pts.push(pts[0]);
      const color = bar.mark === "05" ? C.tie : C.rebar;
      for (let i = 0; i + 1 < pts.length; i++) {
        this.group.add(segment(pts[i], pts[i + 1], bar.dia * k, color));
      }
    });
    // گروت و صفحه کف روی هر ستون
    m.pedestals.forEach((p) => {
      const side = Math.min((m.base_plate || 0) || 600, p.size - 50) * k;
      const gr = (m.grout || 50) * k, pt = (m.plate_t || 20) * k;
      const g = box(side + 0.05, gr, side + 0.05, C.grout);
      g.position.set(p.x * k, top + gr / 2, -p.y * k);
      this.group.add(g);
      const pl = box(side, pt, side, C.plate);
      pl.material.metalness = 0.3;
      pl.position.set(p.x * k, top + gr + pt / 2, -p.y * k);
      this.group.add(pl);
    });
    m.anchors.forEach((a) => {
      this.group.add(segment(P([a.x, a.y, a.z_bottom]), P([a.x, a.y, a.z_top]),
        a.dia * k, C.anchor));
    });

    // سازه فولادی طراحی‌شده در برنامه
    this.steelData = m.steel || [];
    this.equipmentData = m.equipment || [];
    this.k = k;
    this._steel();
    let height = top;
    this.steelData.forEach((s) => { height = Math.max(height, s.p[2] * k, s.q[2] * k); });
    this.equipmentData.forEach((s) => { height = Math.max(height, s.p[2] * k, s.q[2] * k); });

    this.group.position.y = -height / 2;
    this.dist = Math.max(4.5, Math.max(L, B) * 2.6, height * 2.1);
    this.build0 = 0;                 // شروع انیمیشن ساخت
    this.autoRotate = true;
    const empty = this.el.querySelector(".empty");
    if (empty) empty.style.display = "none";
  };

  Viewer.prototype._steel = function () {
    this.group.children.filter((o) => o.userData.steel).forEach((o) => {
      this.group.remove(o); o.geometry.dispose(); o.material.dispose();
    });
    if (this.steelData && this.steelData.length) {
      this.group.add(steelMesh(this.steelData, this.k, !!this.heat));
    }
    if (this.equipmentData && this.equipmentData.length) {
      this.group.add(equipmentGroup(this.equipmentData, this.k));
    }
  };

  /** نمایش سازه با رنگ نسبت تنش هر عضو، یا رنگ واقعی فولاد */
  Viewer.prototype.setHeat = function (on) {
    this.heat = on;
    if (this.ready) this._steel();
  };

  global.FoundationViewer = Viewer;
})(window);
