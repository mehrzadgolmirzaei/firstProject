/* =====================================================================
   نمای سه‌بعدی فونداسیون — Three.js
   مدل از همان اعدادی ساخته می‌شود که موتور محاسبه بیرون داده:
   بتن مگر، پی، ستون، شبکه آرماتور، خاموت و میل مهار.
   این تنها جای صفحه است که حرکت دارد، و حرکتش پاسخ به عمل کاربر است.
   ===================================================================== */
(function (global) {
  "use strict";

  const C = {
    lean:   0x2A3742,
    pad:    0x8E9AA4,
    pedestal: 0xA9B4BC,
    rebar:  0xB4653A,   // مسی — آرماتور
    tie:    0xC98457,
    anchor: 0x6FA8C7,   // فولادی روشن — میل مهار
    ground: 0x1B2630,
  };

  function Viewer(container) {
    this.el = container;
    this.ready = typeof THREE !== "undefined";
    if (!this.ready) return;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x151E27);
    this.scene.fog = new THREE.Fog(0x151E27, 9, 22);

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
        if (o.material && o.material.transparent) o.material.opacity = this.build0;
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
    });
    return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
  }

  function bar(len, dia, color, axis) {
    const m = new THREE.MeshStandardMaterial({ color, roughness: 0.4, metalness: 0.6 });
    const g = new THREE.CylinderGeometry(dia / 2, dia / 2, len, 8);
    const mesh = new THREE.Mesh(g, m);
    if (axis === "x") mesh.rotation.z = Math.PI / 2;
    if (axis === "z") mesh.rotation.x = Math.PI / 2;
    return mesh;
  }

  /** ساخت مدل از خروجی محاسبه */
  Viewer.prototype.build = function (g) {
    if (!this.ready) return;
    this._clear();
    const L = g.L, B = g.B, tf = g.tf, hp = g.hp, b = g.b;
    const cov = (g.cover || 75) / 1000, lean = (g.lean || 100) / 1000;
    const n = g.n_pedestal || 1;
    const sp = g.pedestal_spacing || (n > 1 ? B / 2 : 0);
    const dia = (g.pad_dia || 14) / 1000;
    const spacing = (g.pad_spacing || 200) / 1000;

    // زمین
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(L * 3.2, B * 3.2),
      new THREE.MeshStandardMaterial({ color: C.ground, roughness: 1 }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -lean - 0.001;
    this.group.add(ground);

    // بتن مگر
    const lc = box(L + 0.2, lean, B + 0.2, C.lean);
    lc.position.y = -lean / 2;
    this.group.add(lc);

    // پی
    const pad = box(L, tf, B, C.pad, 0.55);
    pad.position.y = tf / 2;
    this.group.add(pad);
    const padEdge = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(L, tf, B)),
      new THREE.LineBasicMaterial({ color: 0xD6DEE4 }));
    padEdge.position.y = tf / 2;
    this.group.add(padEdge);

    // شبکه آرماتور پی، دو لایه
    [cov, tf - cov].forEach((y) => {
      for (let x = -L / 2 + cov; x <= L / 2 - cov + 1e-6; x += spacing) {
        const r = bar(B - 2 * cov, dia, C.rebar, "z");
        r.position.set(x, y, 0);
        this.group.add(r);
      }
      for (let z = -B / 2 + cov; z <= B / 2 - cov + 1e-6; z += spacing) {
        const r = bar(L - 2 * cov, dia, C.rebar, "x");
        r.position.set(0, y, z);
        this.group.add(r);
      }
    });

    // ستون‌ها
    const xs = n > 1 ? [-sp / 2, sp / 2] : [0];
    const colDia = (g.col_dia || 18) / 1000;
    const tieSp = (g.tie_spacing || 150) / 1000;
    const core = b - 2 * cov;
    xs.forEach((cx) => {
      const ped = box(b, hp, b, C.pedestal, 0.45);
      ped.position.set(cx, tf + hp / 2, 0);
      this.group.add(ped);
      const edge = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.BoxGeometry(b, hp, b)),
        new THREE.LineBasicMaterial({ color: 0xD6DEE4 }));
      edge.position.set(cx, tf + hp / 2, 0);
      this.group.add(edge);

      // میلگردهای قائم دور مقطع
      const per = Math.max(2, Math.round((g.col_bars || 8) / 4));
      for (let i = 0; i < per; i++) {
        const o = -core / 2 + (core / (per - 1 || 1)) * i;
        [[o, -core / 2], [o, core / 2], [-core / 2, o], [core / 2, o]].forEach((p) => {
          const v = bar(hp + tf - 2 * cov, colDia, C.rebar, "y");
          v.position.set(cx + p[0], (tf + hp) / 2, p[1]);
          this.group.add(v);
        });
      }
      // خاموت‌ها
      for (let y = tf + cov; y <= tf + hp - cov; y += tieSp) {
        const ring = new THREE.LineLoop(
          new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(cx - core / 2, y, -core / 2),
            new THREE.Vector3(cx + core / 2, y, -core / 2),
            new THREE.Vector3(cx + core / 2, y, core / 2),
            new THREE.Vector3(cx - core / 2, y, core / 2)]),
          new THREE.LineBasicMaterial({ color: C.tie }));
        this.group.add(ring);
      }
      // میل مهارها
      const gge = (g.anchor_gauge || 450) / 1000;
      const ad = (g.anchor_dia || 20) / 1000;
      const emb = (g.anchor_embed || 600) / 1000;
      [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach((s) => {
        const ab = bar(emb + 0.2, ad, C.anchor, "y");
        ab.position.set(cx + s[0] * gge / 2, tf + hp - emb / 2 + 0.1, s[1] * gge / 2);
        this.group.add(ab);
      });
    });

    this.group.position.y = -(tf + hp) / 2;
    this.dist = Math.max(4.5, Math.max(L, B) * 2.6);
    this.build0 = 0;                 // شروع انیمیشن ساخت
    this.autoRotate = true;
    const empty = this.el.querySelector(".empty");
    if (empty) empty.style.display = "none";
  };

  global.FoundationViewer = Viewer;
})(window);
