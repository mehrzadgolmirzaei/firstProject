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
  };

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

    this.group.position.y = -top / 2;
    this.dist = Math.max(4.5, Math.max(L, B) * 2.6);
    this.build0 = 0;                 // شروع انیمیشن ساخت
    this.autoRotate = true;
    const empty = this.el.querySelector(".empty");
    if (empty) empty.style.display = "none";
  };

  global.FoundationViewer = Viewer;
})(window);
