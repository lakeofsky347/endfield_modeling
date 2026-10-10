/* 背景特效层：WebGL 绘制，失败自动退回 CSS。只读 <html data-theme="hsr|endfield">，不碰页面逻辑。 */
(function () {
  "use strict";
  var theme = document.documentElement.getAttribute("data-theme") || "hsr";
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- 加载遮罩接口 ---------- */
  function ensureLoader() {
    var el = document.getElementById("loader");
    if (!el) {
      el = document.createElement("div");
      el.id = "loader";
      el.innerHTML = '<div class="ld-mark"></div><div class="ld-text">正在加载数据…</div><div class="ld-err"></div>';
      (document.body || document.documentElement).appendChild(el);
    }
    return el;
  }
  window.__uiReady = function () {
    var el = document.getElementById("loader");
    if (!el) return;
    el.classList.add("done");
    setTimeout(function () { el.remove(); }, 600);
  };
  window.__uiError = function (msg) {
    var el = ensureLoader();
    el.classList.add("error");
    el.querySelector(".ld-text").textContent = "加载失败";
    el.querySelector(".ld-err").textContent = String(msg || "");
  };

  /* ---------- WebGL 背景 ---------- */
  var FRAG = {
    hsr: [
      "precision mediump float;uniform vec2 r;uniform float t;",
      "float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}",
      "float stars(vec2 uv,float s,float sp){vec2 g=uv*s;vec2 id=floor(g);vec2 f=fract(g)-.5;",
      " float n=h(id);vec2 o=vec2(h(id+1.3),h(id+7.1))-.5;float d=length(f-o*.7);",
      " float tw=.6+.4*sin(t*sp+n*40.);return smoothstep(.06*n,.0,d)*step(.82,n)*tw;}",
      "void main(){vec2 uv=gl_FragCoord.xy/r.y;vec2 c=uv-vec2(r.x/r.y*.5,.5);",
      " vec3 col=mix(vec3(.03,.04,.09),vec3(.09,.06,.18),uv.y);",
      " col+=vec3(.25,.18,.55)*.35*exp(-6.*length(c-vec2(-.6,.45)));",
      " col+=vec3(.15,.25,.6)*.30*exp(-5.*length(c-vec2(.7,.35)));",
      " float a=atan(c.y,c.x),l=length(c);",
      " col+=vec3(.55,.6,1.)*.05*smoothstep(.006,0.,abs(l-.62-.01*sin(a*3.+t*.2)));",
      " col+=vec3(.8,.6,1.)*.035*smoothstep(.004,0.,abs(l-.88));",
      " col+=vec3(.9,.92,1.)*(stars(uv+t*.004,60.,1.5)+stars(uv+t*.002,120.,2.3)*.6);",
      " gl_FragColor=vec4(col,1.);}"
    ].join("\n"),
    ww: [
      "precision mediump float;uniform vec2 r;uniform float t;",
      "void main(){vec2 uv=gl_FragCoord.xy/r;vec2 p=(gl_FragCoord.xy-.5*r)/r.y;",
      " vec3 col=mix(vec3(.035,.04,.05),vec3(.07,.075,.085),uv.y);",
      " float w=0.;for(int i=0;i<5;i++){float fi=float(i);",
      "  float y=.06*sin(p.x*(3.+fi*1.7)+t*(.25+fi*.07)+fi*1.3)*(1.-abs(p.x)*.6)-.18+fi*.012;",
      "  w+=smoothstep(.004,0.,abs(p.y-y))*(.35-fi*.05);}",
      " col+=mix(vec3(.85,.72,.42),vec3(.45,.85,.9),uv.x)*w*.55;",
      " float l=length(p-vec2(.55,.22));",
      " for(int k=1;k<5;k++){float rr=float(k)*.09+.01*sin(t*.4+float(k));col+=vec3(.9,.8,.55)*.05*smoothstep(.003,0.,abs(l-rr));}",
      " col+=vec3(.95,.85,.6)*.06*exp(-8.*l);",
      " float v=length(uv-.5);col*=1.-.5*v*v;",
      " gl_FragColor=vec4(col,1.);}"
    ].join("\n"),
    endfield: [
      "precision mediump float;uniform vec2 r;uniform float t;",
      "void main(){vec2 p=gl_FragCoord.xy;vec2 uv=p/r;",
      " vec3 col=vec3(.055,.058,.062)+vec3(.02)*(1.-uv.y);",
      " vec2 g=abs(fract(p/48.)-.5)*48.;float grid=smoothstep(1.,0.,min(g.x,g.y));",
      " vec2 g2=abs(fract(p/240.)-.5)*240.;float big=smoothstep(1.2,0.,min(g2.x,g2.y));",
      " col+=vec3(.09)*grid*.35+vec3(.98,.82,.12)*big*.06;",
      " float sy=fract(t*.06);float scan=exp(-abs(uv.y-1.+sy)*60.);",
      " col+=vec3(.98,.82,.12)*scan*.07;",
      " col*=.94+.06*sin(p.y*1.5);",
      " float v=length(uv-.5);col*=1.-.55*v*v;",
      " gl_FragColor=vec4(col,1.);}"
    ].join("\n")
  };

  function startGL() {
    var cv = document.createElement("canvas");
    cv.id = "bg-gl";
    cv.setAttribute("aria-hidden", "true");
    var gl = cv.getContext("webgl", { antialias: false, alpha: false, powerPreference: "low-power" });
    if (!gl) return false;
    function sh(type, src) { var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null; }
    var vs = sh(gl.VERTEX_SHADER, "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}");
    var fs = sh(gl.FRAGMENT_SHADER, FRAG[theme] || FRAG.hsr);
    if (!vs || !fs) return false;
    var pr = gl.createProgram(); gl.attachShader(pr, vs); gl.attachShader(pr, fs); gl.linkProgram(pr);
    if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) return false;
    gl.useProgram(pr);
    var b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    var uR = gl.getUniformLocation(pr, "r"), uT = gl.getUniformLocation(pr, "t");
    document.body.insertBefore(cv, document.body.firstChild);
    var scale = Math.min(window.devicePixelRatio || 1, 1.5) * 0.75; // 背景不需要满分辨率，省电
    function resize() { cv.width = innerWidth * scale | 0; cv.height = innerHeight * scale | 0; gl.viewport(0, 0, cv.width, cv.height); gl.uniform2f(uR, cv.width, cv.height); }
    addEventListener("resize", resize); resize();
    var t0 = performance.now(), last = 0;
    function frame(now) {
      if (!document.hidden && now - last > 33) { // ~30fps 上限
        last = now; gl.uniform1f(uT, (now - t0) / 1000); gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
      if (!reduce) requestAnimationFrame(frame);
    }
    gl.uniform1f(uT, 0); gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (!reduce) requestAnimationFrame(frame);
    cv.addEventListener("webglcontextlost", function () { cv.remove(); document.documentElement.classList.add("no-gl"); });
    document.documentElement.classList.add("has-gl");
    return true;
  }

  function init() {
    ensureLoader();
    var ok = false;
    try { ok = startGL(); } catch (e) { ok = false; }
    if (!ok) document.documentElement.classList.add("no-gl");
  }
  if (document.body) init(); else document.addEventListener("DOMContentLoaded", init);
})();
