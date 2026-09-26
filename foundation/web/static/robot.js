/* =====================================================================
   کاراکتر ربات صفحه ورود — Three.js
   سری شبیه مانیتور قدیمی که دنبال نشانگر ماوس می‌چرخد.
   وقتی روی کادر ورود بروید سرش را کج می‌کند، و موقع تایپ رمز عبور
   دست‌هایش را جلوی صفحه می‌گیرد تا نگاه نکند.
   ===================================================================== */
(function (global) {
  "use strict";

  const PALETTE = {
    body:   0x2E4A5E,   // بدنه فولادی
    panel:  0x3E6B8A,
    head:   0x27384A,   // قاب مانیتور
    screen: 0x0E2430,
    glow:   0x7FD4C1,   // چشم‌ها
    copper: 0xB4653A,   // لهجه گرم
    trim:   0x8FA9BC,
  };

  function mat(color, opts) {
    return new THREE.MeshStandardMaterial(Object.assign(
      { color, roughness: 0.55, metalness: 0.35 }, opts || {}));
  }

  function boxMesh(w, h, d, material, r) {
    return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  }

  function Robot(canvas) {
    if (typeof THREE === "undefined") return;
    this.canvas = canvas;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.1, 50);
    this.camera.position.set(0, 0.25, 7.2);

    this.scene.add(new THREE.HemisphereLight(0xBFD9E8, 0x16202B, 0.9));
    const key = new THREE.DirectionalLight(0xFFF1E4, 1.0);
    key.position.set(2.5, 4, 4);
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0x6FA8C7, 0.55);
    rim.position.set(-3, 1.5, -2);
    this.scene.add(rim);

    this.root = new THREE.Group();
    this.scene.add(this.root);
    this._build();

    this.target = { x: 0, y: 0 };
    this.look = { x: 0, y: 0 };
    this.shy = 0;          // ۰ عادی ، ۱ دست جلوی صفحه
    this.lean = 0;         // وقتی ماوس روی کادر است
    this.t = 0;
    this.blink = 0;
    this.nextBlink = 2 + Math.random() * 3;
    this.fx = null;        // واکنش جاری به کلیک
    this.fxIndex = 0;

    this._resize();
    addEventListener("resize", () => this._resize());
    this._loop();
  }

  Robot.prototype._build = function () {
    const bodyMat = mat(PALETTE.body);
    const panelMat = mat(PALETTE.panel);
    const headMat = mat(PALETTE.head, { roughness: 0.4 });
    const trimMat = mat(PALETTE.trim, { metalness: 0.6 });
    const copperMat = mat(PALETTE.copper, { metalness: 0.5, roughness: 0.4 });

    // --- بدنه ---
    const torso = boxMesh(1.5, 1.35, 0.85, bodyMat);
    torso.position.y = -0.75;
    this.root.add(torso);

    const chest = boxMesh(0.78, 0.42, 0.06, panelMat);
    chest.position.set(0, -0.55, 0.44);
    this.root.add(chest);
    for (let i = 0; i < 3; i++) {
      const led = new THREE.Mesh(
        new THREE.CircleGeometry(0.045, 12),
        new THREE.MeshBasicMaterial({ color: i === 0 ? PALETTE.copper : PALETTE.glow }));
      led.position.set(-0.22 + i * 0.22, -0.55, 0.48);
      this.root.add(led);
    }

    // یقه
    const collar = boxMesh(1.05, 0.16, 0.7, trimMat);
    collar.position.y = -0.02;
    this.root.add(collar);

    // --- بازوها ---
    this.arms = [];
    [-1, 1].forEach((s) => {
      const arm = new THREE.Group();
      const upper = boxMesh(0.26, 0.78, 0.26, bodyMat);
      upper.position.y = -0.39;
      arm.add(upper);
      const fore = new THREE.Group();
      const lower = boxMesh(0.22, 0.62, 0.22, panelMat);
      lower.position.y = -0.31;
      fore.add(lower);
      const hand = boxMesh(0.3, 0.24, 0.3, trimMat);
      hand.position.y = -0.72;
      fore.add(hand);
      fore.position.y = -0.78;
      arm.add(fore);
      arm.position.set(s * 0.92, -0.18, 0);
      arm.userData = { side: s, fore };
      this.root.add(arm);
      this.arms.push(arm);
    });

    // --- سر: مانیتور قدیمی ---
    this.head = new THREE.Group();
    this.head.position.y = 0.72;
    this.root.add(this.head);

    const neck = boxMesh(0.3, 0.24, 0.3, trimMat);
    neck.position.y = -0.5;
    this.head.add(neck);

    const shell = boxMesh(1.62, 1.3, 1.25, headMat);
    this.head.add(shell);

    // لبه‌های قاب
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(1.62, 1.3, 1.25)),
      new THREE.LineBasicMaterial({ color: 0x5E7C93 }));
    this.head.add(edges);

    // صفحه نمایش، کمی فرورفته
    const screen = boxMesh(1.2, 0.92, 0.06, new THREE.MeshBasicMaterial({ color: PALETTE.screen }));
    screen.position.z = 0.62;
    this.head.add(screen);
    const bezel = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(1.24, 0.96, 0.02)),
      new THREE.LineBasicMaterial({ color: PALETTE.trim }));
    bezel.position.z = 0.655;
    this.head.add(bezel);

    // چشم‌ها
    this.eyes = [];
    [-1, 1].forEach((s) => {
      const eye = new THREE.Mesh(
        new THREE.CircleGeometry(0.15, 20),
        new THREE.MeshBasicMaterial({ color: PALETTE.glow }));
      eye.position.set(s * 0.28, 0.06, 0.67);
      this.head.add(eye);
      this.eyes.push(eye);
    });

    // خط اسکن
    this.scan = new THREE.Mesh(
      new THREE.PlaneGeometry(1.18, 0.05),
      new THREE.MeshBasicMaterial({ color: 0x6FA8C7, transparent: true, opacity: 0.22 }));
    this.scan.position.z = 0.665;
    this.head.add(this.scan);

    // آنتن با گوی مسی
    const rod = new THREE.Mesh(
      new THREE.CylinderGeometry(0.028, 0.028, 0.5, 8), trimMat);
    rod.position.y = 0.88;
    this.head.add(rod);
    const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.1, 16, 12), copperMat);
    bulb.position.y = 1.16;
    this.head.add(bulb);
    this.bulb = bulb;

    // دکمه‌های زیر صفحه
    for (let i = 0; i < 2; i++) {
      const knob = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.05, 12), trimMat);
      knob.rotation.x = Math.PI / 2;
      knob.position.set(-0.4 + i * 0.22, -0.52, 0.64);
      this.head.add(knob);
    }
  };

  Robot.prototype._resize = function () {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
  };

  /** نشانگر ماوس در مختصات نرمال‌شده صفحه */
  Robot.prototype.pointTo = function (clientX, clientY) {
    const r = this.canvas.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    this.target.x = Math.max(-1.4, Math.min(1.4, (clientX - cx) / (innerWidth * 0.35)));
    this.target.y = Math.max(-1, Math.min(1, (clientY - cy) / (innerHeight * 0.45)));
  };

  /** واکنش به کلیک — هر بار یکی از حالت‌ها، به ترتیب چرخشی با کمی تصادف */
  Robot.prototype.react = function (kind) {
    const kinds = ["startle", "shake", "spin", "wave", "nod"];
    if (!kind) {
      this.fxIndex = (this.fxIndex + 1 + (Math.random() < 0.35 ? 1 : 0)) % kinds.length;
      kind = kinds[this.fxIndex];
    }
    const dur = { startle: 1.1, shake: 0.9, spin: 1.0, wave: 1.2, nod: 0.8 }[kind] || 1;
    this.fx = { kind, t: 0, dur };
    if (kind === "startle") {
      this.blink = 0; this.nextBlink = 1.6;
      this.eyes.forEach(e => e.scale.set(1.5, 1.5, 1));
    }
  };

  Robot.prototype.setShy = function (on) { this.shyTarget = on ? 1 : 0; };
  Robot.prototype.setLean = function (on) { this.leanTarget = on ? 1 : 0; };

  Robot.prototype._loop = function () {
    requestAnimationFrame(() => this._loop());
    const dt = 0.016;
    this.t += dt;

    // نرم کردن حرکت سر
    this.look.x += (this.target.x - this.look.x) * 0.09;
    this.look.y += (this.target.y - this.look.y) * 0.09;
    this.shy += ((this.shyTarget || 0) - this.shy) * 0.12;
    this.lean += ((this.leanTarget || 0) - this.lean) * 0.1;

    const hide = this.shy;
    this.head.rotation.y = this.look.x * 0.62 * (1 - hide * 0.6);
    this.head.rotation.x = this.look.y * 0.34 * (1 - hide) + hide * 0.22
                          + Math.sin(this.t * 1.6) * 0.012;
    this.head.rotation.z = -this.look.x * 0.08 + this.lean * 0.1;

    // تنفس و تکان بدن
    this.root.position.y = Math.sin(this.t * 1.5) * 0.035 - this.lean * 0.05;
    this.root.rotation.y = this.look.x * 0.16;

    // چشم‌ها کمی مستقل حرکت می‌کنند
    this.eyes.forEach((eye, i) => {
      eye.position.x = (i === 0 ? -0.28 : 0.28) + this.look.x * 0.05;
      eye.position.y = 0.06 - this.look.y * 0.04;
    });

    // پلک زدن
    this.nextBlink -= dt;
    if (this.nextBlink <= 0) {
      this.blink = 1;
      this.nextBlink = 2.5 + Math.random() * 3.5;
    }
    if (this.blink > 0) {
      this.blink = Math.max(0, this.blink - dt * 7);
      const s = 1 - Math.sin((1 - this.blink) * Math.PI) * 0.92;
      this.eyes.forEach(e => e.scale.y = Math.max(0.06, s));
    }

    // خط اسکن روی صفحه
    this.scan.position.y = ((this.t * 0.45) % 1) * 0.9 - 0.45;

    // گوی آنتن نبض می‌زند
    const p = 1 + Math.sin(this.t * 2.4) * 0.08;
    this.bulb.scale.set(p, p, p);

    // بازوها: عادی کنار بدن، موقع تایپ رمز جلوی صفحه
    this.arms.forEach((arm) => {
      const s = arm.userData.side;
      const idle = Math.sin(this.t * 1.4 + s) * 0.05;
      arm.rotation.z = s * (0.12 + idle) * (1 - hide) + hide * s * -1.35;
      arm.rotation.x = hide * -0.55;
      arm.userData.fore.rotation.x = hide * -1.15 - 0.06;
      arm.userData.fore.rotation.z = hide * s * 0.35;
    });

    // ---------- واکنش به کلیک ----------
    let armWave = 0;
    if (this.fx) {
      const f = this.fx;
      f.t += dt;
      const k = Math.min(1, f.t / f.dur);        // پیشرفت ۰ تا ۱
      const ease = 1 - Math.pow(1 - k, 3);
      const decay = Math.exp(-k * 5);

      if (f.kind === "startle") {
        // می‌پرد عقب و بالا، بعد آرام برمی‌گردد
        this.root.position.z = -0.9 * Math.sin(Math.PI * ease) ;
        this.root.position.y += 0.28 * Math.sin(Math.PI * ease);
        this.head.rotation.x -= 0.3 * Math.sin(Math.PI * ease);
        this.root.rotation.z = Math.sin(f.t * 32) * 0.05 * decay;
        this.bulb.material.color.setHex(k < 0.55 ? 0xE4703F : PALETTE.copper);
        const w = 1 + 0.5 * Math.sin(Math.PI * ease);
        this.eyes.forEach(e => e.scale.set(w, w, 1));
      } else if (f.kind === "shake") {
        this.head.rotation.y += Math.sin(f.t * 26) * 0.42 * decay;
      } else if (f.kind === "spin") {
        this.head.rotation.y += Math.PI * 2 * ease;
        this.head.rotation.z += Math.sin(Math.PI * ease) * 0.15;
      } else if (f.kind === "wave") {
        armWave = Math.sin(Math.PI * ease);
      } else if (f.kind === "nod") {
        this.head.rotation.x += Math.sin(f.t * 22) * 0.3 * decay;
      }

      if (k >= 1) {
        this.fx = null;
        this.root.position.z = 0;
        this.root.rotation.z = 0;
        this.bulb.material.color.setHex(PALETTE.copper);
        this.eyes.forEach(e => e.scale.set(1, 1, 1));
      }
    }

    if (armWave) {
      // بازوی سمت چپِ تصویر (side = -1): از کنار بدنه بالا می‌آید، نه از پشت.
      // چرخش مثبت حول z بازو را از بدنه دور می‌کند.
      const arm = this.arms.find(a => a.userData.side === -1);
      if (arm) {
        arm.rotation.z = 2.25 * armWave;
        arm.rotation.x = 0.18 * armWave;      // کمی رو به جلو تا از پشت رد نشود
        arm.rotation.y = 0;
        arm.userData.fore.rotation.x = -0.25 * armWave;
        arm.userData.fore.rotation.z = Math.sin(this.t * 16) * 0.55 * armWave;
      }
    }

    this.renderer.render(this.scene, this.camera);
  };

  global.LoginRobot = Robot;
})(window);
