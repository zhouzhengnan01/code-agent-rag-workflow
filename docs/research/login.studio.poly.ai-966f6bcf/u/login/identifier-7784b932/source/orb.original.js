/* Listening orb: GPGPU particle sim on raw WebGL2, no dependencies.
   Ping-pong position/velocity textures, additive point pass, bloom, composite.
   Driven by focus and submit events on the widget. */
(function () {
  var host = document.getElementById('orb');
  if (!host) return;

  /* No orb on phones. Nothing is built until we are above the breakpoint, so
     a phone pays nothing for context creation, shader compilation or the
     texture uploads. */
  var ORB_MIN_WIDTH = 761;
  var gl = null, glDead = false;
  function context() {
    if (gl || glDead) return gl;
    gl = host.getContext('webgl2', {
      alpha: true, antialias: false, depth: false,
      premultipliedAlpha: true, powerPreference: 'low-power'
    });
    /* No WebGL2 or float render targets: fall through, the page keeps its
       grain background. */
    if (!gl || !gl.getExtension('EXT_color_buffer_float')) { gl = null; glDead = true; }
    return gl;
  }

  var SIDE = 181, COUNT = SIDE * SIDE;
  var reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  var COMMON = [
    'precision highp float;',
    'precision highp sampler2D;',
    'float hash11(float p){p=fract(p*0.1031);p*=p+33.33;p*=p+p;return fract(p);}',
    'float hash13(vec3 p){p=fract(p*0.1031);p+=dot(p,p.yzx+33.33);return fract((p.x+p.y)*p.z);}',
    'float noise3(vec3 p){vec3 c=floor(p),l=fract(p);l=l*l*(3.0-2.0*l);',
    'float n000=hash13(c),n100=hash13(c+vec3(1,0,0)),n010=hash13(c+vec3(0,1,0)),n110=hash13(c+vec3(1,1,0));',
    'float n001=hash13(c+vec3(0,0,1)),n101=hash13(c+vec3(1,0,1)),n011=hash13(c+vec3(0,1,1)),n111=hash13(c+vec3(1,1,1));',
    'float x00=mix(n000,n100,l.x),x10=mix(n010,n110,l.x),x01=mix(n001,n101,l.x),x11=mix(n011,n111,l.x);',
    'return mix(mix(x00,x10,l.y),mix(x01,x11,l.y),l.z)*2.0-1.0;}',
    'vec3 curlNoise(vec3 p){float e=0.12;',
    'float dx1=noise3(p+vec3(e,0,0)),dx2=noise3(p-vec3(e,0,0));',
    'float dy1=noise3(p+vec3(0,e,0)),dy2=noise3(p-vec3(0,e,0));',
    'float dz1=noise3(p+vec3(0,0,e)),dz2=noise3(p-vec3(0,0,e));',
    'return vec3(dz1-dz2,dx1-dx2,dy1-dy2)*0.5;}',
    /* Uniform point on the sphere, slowly wobbling radius, rogue tail on the
       top ~14%. */
    'vec3 orbNormal(float s){float lon=hash11(s*12.41+0.8)*6.28318530718;',
    'float h=hash11(s*18.73+3.4)*2.0-1.0;float r=sqrt(max(0.0,1.0-h*h));',
    'return vec3(cos(lon)*r,h,sin(lon)*r);}',
    'vec3 orbTarget(float s,float t,float breathe){vec3 n=orbNormal(s);float tt=t*0.16;',
    'float broad=noise3(n*2.7+vec3(tt*0.3,-tt*0.18,tt*0.24));',
    'float fine=sin(n.x*4.4+n.z*2.2+s*13.0+t*0.12);',
    'float r=(3.36+broad*0.22+fine*0.045)*breathe;',
    'float rs=hash11(s*23.71+8.9);float rogue=smoothstep(0.86,0.985,rs);',
    'float ra=s*5.73+t*(0.08+rs*0.05);',
    'vec3 ta=normalize(cross(n,vec3(0,0,1))+vec3(0.0001));',
    'vec3 tb=normalize(cross(n,ta)+vec3(0.0001));',
    'vec3 rd=normalize(n*0.42+ta*cos(ra)+tb*sin(ra));',
    'float rdist=rogue*(0.46+hash11(s*31.17+2.4)*0.82);',
    'return n*r+rd*rdist;}'
  ].join('\n');

  var QUAD_VS = '#version 300 es\nin vec2 aP;out vec2 vUv;void main(){vUv=aP*0.5+0.5;gl_Position=vec4(aP,0,1);}';

  /* Shared by both sim targets; position reuses the velocity integrator. */
  var SIM_BODY = [
    'uniform sampler2D uPos;uniform sampler2D uVel;',
    'uniform float uTime,uDelta,uTighten,uPulse,uPulseAge,uBreathe;',
    'uniform vec4 uPointer;uniform vec3 uPointerVel;uniform float uPointerRadius,uVoice;',
    'in vec2 vUv;out vec4 outColor;',
    'vec3 velocityStep(vec3 pos,vec3 vel,float seed){',
    '  vec3 target=orbTarget(seed,uTime,uBreathe);',
    '  vec3 n=normalize(pos+vec3(0.0001));',
    '  vec3 ccw=normalize(cross(vec3(0,0,1),n));',
    '  vec3 lat=normalize(cross(n,ccw));',
    '  vec3 np=n*3.6+vec3(seed*2.1,seed*1.4,seed*2.8);',
    '  vec3 wander=curlNoise(np+vec3(uTime*0.08,-uTime*0.05,uTime*0.07));',
    '  float flow=noise3(np-vec3(uTime*0.06,uTime*0.04,-uTime*0.05));',
    '  float cohesionNoise=hash11(seed*9.17+5.8);',
    '  float stray=smoothstep(0.68,0.94,cohesionNoise);',
    '  float rogue=smoothstep(0.86,0.985,hash11(seed*23.71+8.9));',
    '  float cohesion=mix(mix(1.12,0.42,stray),0.22,rogue);',
    /* On focus the shell tightens and the wander drops. */
    '  cohesion*=1.0+uTighten*0.85;',
    '  float motion=mix(1.0,0.55,uTighten);',
    '  vec3 ifp=pos*vec3(0.22,0.2,0.18)+vec3(uTime*0.44,-uTime*0.31,uTime*0.36)+vec3(seed*2.7,seed*1.9,seed*2.8);',
    '  vec3 broadFlow=curlNoise(ifp);',
    '  vec3 fineFlow=curlNoise(ifp*1.9-vec3(uTime*0.42,-uTime*0.34,uTime*0.28));',
    '  vec3 force=(target-pos)*(1.45*cohesion);',
    '  force+=broadFlow*0.62*motion;',
    '  force+=fineFlow*0.18*motion;',
    '  force+=ccw*(0.7+flow*0.2)*motion;',
    '  force+=lat*flow*0.18*motion;',
    '  force+=wander*(0.35+stray*0.24+rogue*0.42)*motion;',
    '  force+=n*rogue*(0.32+flow*0.16)*motion;',
    /* Keystrokes add a small ripple. */
    '  force+=n*uVoice*sin(seed*61.7+uTime*5.4)*0.55;',
    /* Submit: a displacement wave travels outward. */
    '  float radius=length(pos);',
    '  float frontEdge=uPulseAge*7.4-radius;',
    '  float wave=exp(-frontEdge*frontEdge*2.2)*uPulse;',
    '  force+=n*wave*7.0;',
    '  force+=ccw*wave*1.6;',
    /* Cursor: radial repel, tangential swirl, and drag from pointer velocity. */
    '  vec3 pd=pos-uPointer.xyz;',
    '  float pinf=exp(-dot(pd,pd)/max(uPointerRadius*uPointerRadius,0.0001))*uPointer.w;',
    '  force+=normalize(pd+vec3(0.0001))*pinf*1.55*motion;',
    '  vec3 ptan=normalize(vec3(-pd.y,pd.x,pd.z*0.12)+vec3(0.0001));',
    '  force+=ptan*pinf*(0.18+length(uPointerVel)*0.12)*motion;',
    '  force+=uPointerVel*pinf*(0.24+motion*0.42);',
    '  force+=-vel*(0.48+cohesion*0.22);',
    '  vec3 next=vel+force*uDelta;',
    '  float maxSpeed=1.35+stray*0.42+uPulse*1.6;',
    '  return length(next)>maxSpeed?normalize(next)*maxSpeed:next;',
    '}'
  ].join('\n');

  var VEL_FS = '#version 300 es\n' + COMMON + '\n' + SIM_BODY + [
    'void main(){vec4 p=texture(uPos,vUv);vec4 v=texture(uVel,vUv);',
    'outColor=vec4(velocityStep(p.xyz,v.xyz,v.w),v.w);}'
  ].join('\n');

  var POS_FS = '#version 300 es\n' + COMMON + '\n' + SIM_BODY + [
    'void main(){vec4 p=texture(uPos,vUv);vec4 v=texture(uVel,vUv);',
    'vec3 nv=velocityStep(p.xyz,v.xyz,v.w);',
    'outColor=vec4(p.xyz+nv*uDelta,p.w);}'
  ].join('\n');

  /* Particle pass: depth, edge weighting, cool/white ramp. */
  var DRAW_VS = '#version 300 es\n' + COMMON + '\n' + [
    'in float aIndex;uniform sampler2D uPos;uniform sampler2D uVel;',
    'uniform vec2 uRes,uOffset;uniform float uTime,uPointSize,uTighten,uPulse,uPulseAge,uAspect,uScale;',
    'out float vDensity,vDepthF,vLight,vSeed,vSpeed,vWave;',
    'void main(){',
    ' vec2 uv=(vec2(mod(aIndex,' + SIDE + '.0),floor(aIndex/' + SIDE + '.0))+0.5)/' + SIDE + '.0;',
    ' vec4 p=texture(uPos,uv);vec4 v=texture(uVel,uv);float seed=v.w;',
    /* Slow orbit. */
    ' float a=uTime*0.055;',
    ' float ca=cos(a),sa=sin(a);',
    ' vec3 wp=vec3(p.x*ca+p.z*sa,p.y,-p.x*sa+p.z*ca);',
    ' wp.y+=sin(uTime*0.21)*0.09;',
    ' float depth=12.2-wp.z;',
    ' vDepthF=clamp(1.35-depth/18.0,0.55,1.08);',
    ' vec3 n=normalize(p.xyz+vec3(0.0001));',
    ' vec3 ld=normalize(vec3(-0.35,0.24,0.9));',
    ' vLight=max(dot(n,ld),0.0);',
    ' float front=smoothstep(-0.95,0.34,n.z);',
    ' float edge=smoothstep(0.06,1.02,length(n.xy));',
    ' float variation=fract(sin(seed*27.1+4.6)*43758.5);',
    /* Interior floor lifted so the shell is not hollow behind the headline.
       Rim ceiling unchanged, so overall brightness is unaffected. */
    ' float surf=(0.5+edge*0.5)*(0.58+front*0.42)*(0.72+vLight*0.28)*(0.84+variation*0.26);',
    ' float vol=0.5+0.5*noise3(p.xyz*0.72+vec3(seed*0.37,seed*0.19,seed*0.53));',
    ' vDensity=clamp(0.14+surf*(0.76+vol*0.26),0.0,1.0);',
    ' float radius=length(p.xyz);',
    ' float fe=uPulseAge*7.4-radius;',
    ' vWave=exp(-fe*fe*2.2)*uPulse;',
    ' vSpeed=length(v.xyz);vSeed=seed;',
    /* Perspective divide by hand: fov 42 at z=12.2. */
    ' float f=1.0/tan(0.3665);',
    ' wp*=uScale;',
    ' gl_Position=vec4(wp.x*f/uAspect+uOffset.x*depth,wp.y*f+uOffset.y*depth,depth*0.02,depth);',
    ' gl_PointSize=uPointSize*(0.84+variation*0.28)*(0.78+vDepthF*0.22)*(1.0+vWave*0.5)*(12.2/depth)*uScale*uRes.y/900.0;',
    '}'
  ].join('\n');

  var DRAW_FS = '#version 300 es\nprecision highp float;' + [
    'in float vDensity,vDepthF,vLight,vSeed,vSpeed,vWave;',
    'uniform float uTime,uTighten;out vec4 outColor;',
    'void main(){',
    ' vec2 c=gl_PointCoord-0.5;',
    ' float e=1.0-smoothstep(0.16,0.5,length(c));',
    ' if(e<=0.0) discard;',
    ' float rate=0.22+fract(vSeed*17.31)*0.3;',
    ' float pulse=0.5+0.5*sin(uTime*rate+vSeed*91.731);',
    ' float grain=mix(0.30,1.0,vDensity)*(0.84+vDepthF*0.16);',
    ' float alpha=e*grain*(0.14+vDensity*0.86)*mix(0.52,1.15,vDepthF);',
    ' vec3 cool=vec3(0.12,0.24,0.42);',
    ' vec3 white=vec3(0.86,0.95,1.0);',
    ' vec3 color=mix(cool,white,clamp(0.22+pow(vDensity,1.4)*0.72+vSpeed*0.05,0.0,1.0));',
    ' color*=0.74+vLight*0.26;',
    ' color*=0.86+vDepthF*0.14;',
    /* Only the wave crest goes fully bright. */
    ' color=mix(color,vec3(0.94,0.98,1.0),clamp(vWave*0.9,0.0,1.0));',
    ' alpha*=(0.06+pow(vDensity,1.75)*0.72)*(0.78+pulse*0.22);',
    ' alpha*=1.0+vWave*3.4+uTighten*0.28;',
    ' if(alpha<0.003) discard;',
    ' outColor=vec4(color*alpha,alpha);',
    '}'
  ].join('\n');

  /* Broad dim light pools. Positions derive from the light index and clock,
     so there is no buffer to update. */
  var LIGHTS = 10;
  var LIGHT_VS = '#version 300 es\n' + COMMON + '\n' + [
    'in float aIndex;uniform vec2 uRes,uOffset;uniform float uTime,uAspect,uScale,uMaxPoint,uTighten;',
    'out float vI;',
    'void main(){',
    ' float i=aIndex;float s=hash11(i*3.17+1.7);float s2=hash11(i*7.31+4.2);',
    ' float rad=(1.2+s*2.4)*mix(1.0,0.86,uTighten);',
    ' float sp=0.05+s2*0.08;',
    ' vec3 p=vec3(cos(uTime*sp+i*2.3)*rad, sin(uTime*sp*0.82+i*1.7)*rad*0.78, sin(uTime*sp*0.66+i*3.1)*rad);',
    ' float depth=12.2-p.z;',
    ' p*=uScale;',
    ' float f=1.0/tan(0.3665);',
    ' gl_Position=vec4(p.x*f/uAspect+uOffset.x*depth,p.y*f+uOffset.y*depth,depth*0.02,depth);',
    ' gl_PointSize=min(uMaxPoint,(160.0+s*240.0)*uScale*(12.2/depth)*uRes.y/900.0);',
    ' vI=0.5+s2*0.5;',
    '}'
  ].join('\n');

  var LIGHT_FS = '#version 300 es\nprecision highp float;' + [
    'in float vI;uniform float uPulse;out vec4 outColor;',
    'void main(){',
    ' vec2 c=gl_PointCoord-0.5;float d=length(c)*2.0;',
    ' float a=exp(-d*d*3.0)*vI*(0.026+uPulse*0.02);',
    ' if(a<0.0005) discard;',
    ' outColor=vec4(vec3(0.40,0.55,0.78)*a,a);',
    '}'
  ].join('\n');

  var BLUR_FS = '#version 300 es\nprecision highp float;' + [
    'uniform sampler2D uTex;uniform vec2 uDir;in vec2 vUv;out vec4 outColor;',
    'void main(){vec4 s=texture(uTex,vUv)*0.227;',
    's+=(texture(uTex,vUv+uDir*1.3846)+texture(uTex,vUv-uDir*1.3846))*0.316;',
    's+=(texture(uTex,vUv+uDir*3.2307)+texture(uTex,vUv-uDir*3.2307))*0.070;',
    'outColor=s;}'
  ].join('\n');

  var COMP_FS = '#version 300 es\nprecision highp float;' + [
    'uniform sampler2D uCore;uniform sampler2D uGlow;',
    'uniform float uTime,uExposure,uBloom;uniform vec2 uRes;',
    'in vec2 vUv;out vec4 outColor;',
    'float grainNoise(vec2 uv){vec2 p=uv*uRes*0.5;',
    'float t=floor(uTime*24.0);',
    'return fract(sin(dot(p+t,vec2(12.9898,78.233)))*43758.5453)-0.5;}',
    'void main(){',
    ' vec3 core=texture(uCore,vUv).rgb;',
    ' vec3 glow=texture(uGlow,vUv).rgb;',
    /* Grain applies to the bloom, not the whole frame, so the blacks stay black. */
    ' float lum=dot(glow,vec3(0.2126,0.7152,0.0722));',
    ' float mask=smoothstep(0.0002,0.02,lum);',
    ' glow+=glow*grainNoise(vUv)*2.4*mask;',
    ' vec3 color=core*1.18+glow*uBloom;',
    ' vec2 cc=vUv-0.5;',
    ' color*=smoothstep(0.98,0.22,length(cc*vec2(0.86,0.96)));',
    ' color*=uExposure;',
    ' color=color/(1.0+color);',
    ' color=pow(max(color,vec3(0.0)),vec3(0.92));',
    ' float a=clamp(dot(color,vec3(0.3,0.6,0.1))*3.4,0.0,1.0);',
    ' outColor=vec4(color,a);',
    '}'
  ].join('\n');

  function compile(type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(s) + '\n' + src);
    }
    return s;
  }
  function program(vs, fs) {
    var p = gl.createProgram();
    gl.attachShader(p, compile(gl.VERTEX_SHADER, vs));
    gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    var u = {}, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (var i = 0; i < n; i++) {
      var name = gl.getActiveUniform(p, i).name.replace('[0]', '');
      u[name] = gl.getUniformLocation(p, name);
    }
    p.u = u;
    return p;
  }

  var progVel, progPos, progDraw, progBlur, progComp, progLight;
  var quadVao, quadBuf, pointVao, idxBuf, lightVao, lightBuf, maxPoint = 64;

  function dataTex(side, data) {
    var t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, side, side, 0, gl.RGBA, gl.FLOAT, data);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return t;
  }
  function colorTex(w, h) {
    var t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return t;
  }
  function fbo(tex) {
    var f = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, f);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return f;
  }

  /* Seed near the target so the shell assembles on first paint rather than
     expanding from a point. */
  var posData = new Float32Array(COUNT * 4);
  var velData = new Float32Array(COUNT * 4);
  function h11(p) { p = (p * 0.1031) % 1; p *= p + 33.33; p *= p + p; return p - Math.floor(p); }
  for (var j = 0; j < COUNT; j++) {
    var sd = j / COUNT;
    var lon = h11(sd * 12.41 + 0.8) * Math.PI * 2;
    var hh = h11(sd * 18.73 + 3.4) * 2 - 1;
    var rr = Math.sqrt(Math.max(0, 1 - hh * hh));
    var rad = 3.36 * (0.55 + h11(sd * 3.1) * 0.6);
    posData[j * 4] = Math.cos(lon) * rr * rad;
    posData[j * 4 + 1] = hh * rad;
    posData[j * 4 + 2] = Math.sin(lon) * rr * rad;
    posData[j * 4 + 3] = 1;
    velData[j * 4] = (h11(sd * 7.13 + 1.2) - 0.5) * 0.42;
    velData[j * 4 + 1] = (h11(sd * 8.37 + 2.4) - 0.5) * 0.32;
    velData[j * 4 + 2] = (h11(sd * 6.13 + 8.5) - 0.5) * 0.3;
    velData[j * 4 + 3] = sd;
  }

  var posA, posB, velA, velB, posFboA, posFboB, velFboA, velFboB;

  /* All GPU resources in one place so a context restore can rebuild them. */
  function buildGL() {
    try {
      progVel = program(QUAD_VS, VEL_FS);
      progPos = program(QUAD_VS, POS_FS);
      progDraw = program(DRAW_VS, DRAW_FS);
      progBlur = program(QUAD_VS, BLUR_FS);
      progComp = program(QUAD_VS, COMP_FS);
      progLight = program(LIGHT_VS, LIGHT_FS);
    } catch (err) {
      return false; /* fail soft: the grain background carries the page */
    }

    quadVao = gl.createVertexArray();
    gl.bindVertexArray(quadVao);
    quadBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    pointVao = gl.createVertexArray();
    gl.bindVertexArray(pointVao);
    var idx = new Float32Array(COUNT);
    for (var i = 0; i < COUNT; i++) idx[i] = i;
    idxBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, idxBuf);
    gl.bufferData(gl.ARRAY_BUFFER, idx, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 1, gl.FLOAT, false, 0, 0);
    lightVao = gl.createVertexArray();
    gl.bindVertexArray(lightVao);
    var li = new Float32Array(LIGHTS);
    for (var k = 0; k < LIGHTS; k++) li[k] = k;
    lightBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, lightBuf);
    gl.bufferData(gl.ARRAY_BUFFER, li, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 1, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);

    maxPoint = (gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE) || [1, 64])[1] || 64;

    seed();
    sceneTex = null;
    return true;
  }

  function seed() {
    posA = dataTex(SIDE, posData); posB = dataTex(SIDE, null);
    velA = dataTex(SIDE, velData); velB = dataTex(SIDE, null);
    posFboA = fbo(posA); posFboB = fbo(posB);
    velFboA = fbo(velA); velFboB = fbo(velB);
  }



  var W = 0, H = 0, BW = 0, BH = 0, dpr = 1, dprCap = 0;
  var offX = -0.42, offY = 0, scale = 1, exposure = 1.32;
  var sceneTex, sceneFbo, blurTexA, blurFboA, blurTexB, blurFboB;

  /* Orb placement per breakpoint; it lives in the fixed atmosphere layer. */
  var heroEl = document.querySelector('.hero');
  function layout(cssWidth, cssHeight) {
    /* Derived from the headline's box: the layout is width-capped and centred,
       so a fixed offset would only be correct at one width. */
    if (cssWidth > 1100) {
      var cx = cssWidth * 0.26, cy = cssHeight * 0.5;
      if (heroEl) {
        var b = heroEl.getBoundingClientRect();
        cx = b.left + b.width * 0.5;
        cy = b.top + b.height * 0.5;
      }
      offX = (cx / cssWidth) * 2 - 1;
      offY = 1 - (cy / cssHeight) * 2;
      scale = 0.78; exposure = 0.74;
    } else if (cssWidth > 760) {
      offX = 0; offY = 0.30; scale = 0.54; exposure = 0.68;
    } else {
      /* Large and cropped by the top edge at this size. */
      offX = 0; offY = 0.78; scale = 0.62; exposure = 0.92;
    }
    baseCount = cssWidth > 1100 ? COUNT
      : cssWidth > 760 ? Math.floor(COUNT * 0.72)
      : Math.floor(COUNT * 0.5);
    applyQuality();
  }

  function resize() {
    var box = host.getBoundingClientRect();
    var cap = dprCap || (box.width < 760 ? 1.25 : 1.5);
    dpr = Math.min(window.devicePixelRatio || 1, cap);
    var w = Math.max(1, Math.round(box.width * dpr));
    var h = Math.max(1, Math.round(box.height * dpr));
    if (w === W && h === H) return;
    W = w; H = h;
    layout(box.width, box.height);
    host.width = W; host.height = H;
    BW = Math.max(1, W >> 1); BH = Math.max(1, H >> 1);
    if (sceneTex) {
      gl.deleteTexture(sceneTex); gl.deleteFramebuffer(sceneFbo);
      gl.deleteTexture(blurTexA); gl.deleteFramebuffer(blurFboA);
      gl.deleteTexture(blurTexB); gl.deleteFramebuffer(blurFboB);
    }
    sceneTex = colorTex(W, H); sceneFbo = fbo(sceneTex);
    blurTexA = colorTex(BW, BH); blurFboA = fbo(blurTexA);
    blurTexB = colorTex(BW, BH); blurFboB = fbo(blurTexB);
  }

  function bind(unit, tex) {
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, tex);
  }
  function drawQuad() {
    gl.bindVertexArray(quadVao);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  /* tighten rises while a field is focused; pulse fires once on submit. */
  var tighten = 0, tightenTarget = 0;
  var pulse = 0, pulseAt = -99, breathe = 1;

  /* Pointer in NDC until mapped into orb space each frame. Smoothed, or the
     particles twitch. */
  var voice = 0;
  var ptrNdcX = 0, ptrNdcY = 0, ptrOn = 0;
  var smX = 0, smY = 0, smOn = 0;
  var pModel = [0, 0, 0], pVel = [0, 0, 0], pHas = false;

  function step(dt, t) {
    tighten += (tightenTarget - tighten) * (1 - Math.exp(-dt * 3.2));

    var ease = 1 - Math.exp(-dt * 13);
    smX += (ptrNdcX - smX) * ease;
    smY += (ptrNdcY - smY) * ease;
    smOn += (ptrOn - smOn) * (1 - Math.exp(-dt * 5));
    /* Un-project at the orb's centre plane, then un-rotate the slow orbit. */
    var fl = 1 / Math.tan(0.3665);
    var wx = (smX - offX) * (W / H) * 12.2 / (fl * scale);
    var wy = ((smY - offY) * 12.2 / (fl * scale)) - Math.sin(t * 0.21) * 0.09;
    var ang = t * 0.055, ca = Math.cos(ang), sa = Math.sin(ang);
    var nx = wx * ca, ny = wy, nz = wx * sa;
    if (pHas && dt > 0) {
      var k = 1 - Math.exp(-dt * 9);
      pVel[0] += (((nx - pModel[0]) / dt) - pVel[0]) * k;
      pVel[1] += (((ny - pModel[1]) / dt) - pVel[1]) * k;
      pVel[2] += (((nz - pModel[2]) / dt) - pVel[2]) * k;
      var sp = Math.hypot(pVel[0], pVel[1], pVel[2]);
      if (sp > 6) { var q = 6 / sp; pVel[0] *= q; pVel[1] *= q; pVel[2] *= q; }
    }
    pModel[0] = nx; pModel[1] = ny; pModel[2] = nz; pHas = true;
    var age = t - pulseAt;
    pulse = age < 1.9 ? Math.exp(-age * 1.9) : 0;
    breathe = 1 + Math.sin(t * 0.31) * 0.012 - tighten * 0.05;
    voice *= Math.exp(-dt * 2.4);

    /* velocity, then position, each into its own ping-pong target */
    gl.viewport(0, 0, SIDE, SIDE);
    gl.disable(gl.BLEND);

    gl.useProgram(progVel);
    gl.uniform1f(progVel.u.uTime, t); gl.uniform1f(progVel.u.uDelta, dt);
    gl.uniform1f(progVel.u.uTighten, tighten); gl.uniform1f(progVel.u.uPulse, pulse);
    gl.uniform1f(progVel.u.uPulseAge, age); gl.uniform1f(progVel.u.uBreathe, breathe);
    gl.uniform4f(progVel.u.uPointer, pModel[0], pModel[1], pModel[2], smOn);
    gl.uniform3f(progVel.u.uPointerVel, pVel[0], pVel[1], pVel[2]);
    gl.uniform1f(progVel.u.uPointerRadius, 1.55);
    gl.uniform1f(progVel.u.uVoice, voice);
    bind(0, posA); bind(1, velA);
    gl.uniform1i(progVel.u.uPos, 0); gl.uniform1i(progVel.u.uVel, 1);
    gl.bindFramebuffer(gl.FRAMEBUFFER, velFboB);
    drawQuad();

    gl.useProgram(progPos);
    gl.uniform1f(progPos.u.uTime, t); gl.uniform1f(progPos.u.uDelta, dt);
    gl.uniform1f(progPos.u.uTighten, tighten); gl.uniform1f(progPos.u.uPulse, pulse);
    gl.uniform1f(progPos.u.uPulseAge, age); gl.uniform1f(progPos.u.uBreathe, breathe);
    gl.uniform4f(progPos.u.uPointer, pModel[0], pModel[1], pModel[2], smOn);
    gl.uniform3f(progPos.u.uPointerVel, pVel[0], pVel[1], pVel[2]);
    gl.uniform1f(progPos.u.uPointerRadius, 1.55);
    gl.uniform1f(progPos.u.uVoice, voice);
    bind(0, posA); bind(1, velA);
    gl.uniform1i(progPos.u.uPos, 0); gl.uniform1i(progPos.u.uVel, 1);
    gl.bindFramebuffer(gl.FRAMEBUFFER, posFboB);
    drawQuad();

    var tp = posA; posA = posB; posB = tp;
    var tf = posFboA; posFboA = posFboB; posFboB = tf;
    var tv = velA; velA = velB; velB = tv;
    var tvf = velFboA; velFboA = velFboB; velFboB = tvf;
  }

  function draw(t) {
    /* particles, additive, into the scene target */
    gl.bindFramebuffer(gl.FRAMEBUFFER, sceneFbo);
    gl.viewport(0, 0, W, H);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.useProgram(progDraw);
    bind(0, posA); bind(1, velA);
    gl.uniform1i(progDraw.u.uPos, 0); gl.uniform1i(progDraw.u.uVel, 1);
    gl.uniform2f(progDraw.u.uRes, W, H);
    gl.uniform1f(progDraw.u.uAspect, W / H);
    gl.uniform1f(progDraw.u.uTime, t);
    gl.uniform1f(progDraw.u.uPointSize, 2.55);
    gl.uniform1f(progDraw.u.uTighten, tighten);
    gl.uniform1f(progDraw.u.uPulse, pulse);
    gl.uniform1f(progDraw.u.uPulseAge, t - pulseAt);
    gl.uniform2f(progDraw.u.uOffset, offX, offY);
    gl.uniform1f(progDraw.u.uScale, scale);
    gl.bindVertexArray(pointVao);
    gl.drawArrays(gl.POINTS, 0, drawCount);

    gl.useProgram(progLight);
    gl.uniform2f(progLight.u.uRes, W, H);
    gl.uniform2f(progLight.u.uOffset, offX, offY);
    gl.uniform1f(progLight.u.uAspect, W / H);
    gl.uniform1f(progLight.u.uScale, scale);
    gl.uniform1f(progLight.u.uTime, t);
    gl.uniform1f(progLight.u.uTighten, tighten);
    gl.uniform1f(progLight.u.uPulse, pulse);
    gl.uniform1f(progLight.u.uMaxPoint, maxPoint);
    gl.bindVertexArray(lightVao);
    gl.drawArrays(gl.POINTS, 0, LIGHTS);

    /* bloom: half res, separable */
    gl.disable(gl.BLEND);
    gl.viewport(0, 0, BW, BH);
    gl.useProgram(progBlur);
    gl.bindFramebuffer(gl.FRAMEBUFFER, blurFboA);
    bind(0, sceneTex); gl.uniform1i(progBlur.u.uTex, 0);
    gl.uniform2f(progBlur.u.uDir, 1 / BW, 0);
    drawQuad();
    gl.bindFramebuffer(gl.FRAMEBUFFER, blurFboB);
    bind(0, blurTexA);
    gl.uniform2f(progBlur.u.uDir, 0, 1 / BH);
    drawQuad();

    /* composite to the canvas */
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, W, H);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(progComp);
    bind(0, sceneTex); bind(1, blurTexB);
    gl.uniform1i(progComp.u.uCore, 0); gl.uniform1i(progComp.u.uGlow, 1);
    gl.uniform2f(progComp.u.uRes, W, H);
    gl.uniform1f(progComp.u.uTime, t);
    gl.uniform1f(progComp.u.uExposure, exposure);
    gl.uniform1f(progComp.u.uBloom, 0.66 + pulse * 0.5);
    drawQuad();
  }

  var last = 0, clock = 0, running = false, raf = 0;
  var baseCount = COUNT, drawCount = COUNT, quality = 0, slowFrames = 0;
  var lost = false;

  /* Degrade resolution first, then particle count. */
  function applyQuality() {
    dprCap = quality >= 1 ? 1.0 : 0;
    drawCount = quality >= 2 ? Math.floor(baseCount * 0.55) : baseCount;
  }
  function degrade() {
    slowFrames = 0;
    if (quality >= 2) return;
    quality++; applyQuality();
    if (quality === 1) { W = 0; resize(); }
  }

  /* Start a rung down on low-end hardware instead of detecting it after ~90
     slow frames. */
  if ((navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 4) {
    quality = 1;
  }

  function frame(now) {
    raf = 0;
    if (!running) return;
    raf = requestAnimationFrame(frame);

    resize();
    var dt = last ? Math.min((now - last) / 1000, 0.05) : 0.016;
    last = now;
    clock += dt;

    if (quality < 2) {
      if (dt > 0.022) { if (++slowFrames > 90) degrade(); }
      else if (slowFrames > 0) { slowFrames--; }
    }

    step(dt, clock);
    draw(clock);
  }
  function start() {
    if (running || reduced || lost || !built) return;
    running = true; last = 0;
    if (!raf) raf = requestAnimationFrame(frame);
  }
  function stop() {
    running = false;
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
  }

  /* A GPU reset otherwise leaves a dead canvas. preventDefault allows a
     restore; stopping falls back to the grain background. */
  host.addEventListener('webglcontextlost', function (e) {
    e.preventDefault(); lost = true; stop();
  }, false);
  host.addEventListener('webglcontextrestored', function () {
    lost = false;
    if (buildGL()) { W = 0; resize(); start(); }
  }, false);

  var built = false, warmed = false;

  function boot() {
    if (window.innerWidth < ORB_MIN_WIDTH) {
      stop();
      host.style.display = 'none';
      return;
    }
    host.style.display = '';
    if (!context()) return;
    if (!built) {
      if (!buildGL()) { host.style.display = 'none'; return; }
      built = true;
    }
    resize();
    if (reduced) {
      if (!warmed) {
        /* Warm up to a settled state, then hold one frame. */
        for (var w = 0; w < 220; w++) step(0.016, w * 0.016);
        clock = 3.5;
        warmed = true;
      }
      draw(clock);
    } else {
      start();
    }
  }

  boot();
  window.addEventListener('resize', boot);
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) stop(); else boot();
  });

  /* Auth0 renders the widget after this script runs, so listen on the
     document rather than binding to the inputs. */
  document.addEventListener('keydown', function (e) {
    if (!reduced && e.target.closest && e.target.closest('.widget-frame')) {
      voice = Math.min(0.5, voice + 0.16);
    }
  }, true);

  document.addEventListener('focusin', function (e) {
    if (e.target.closest && e.target.closest('.widget-frame')) tightenTarget = 1;
  });
  document.addEventListener('focusout', function () { tightenTarget = 0; });
  /* No cursor reaction under reduced motion. */
  if (!reduced) {
    window.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch') return;
      ptrNdcX = (e.clientX / window.innerWidth) * 2 - 1;
      ptrNdcY = 1 - (e.clientY / window.innerHeight) * 2;
      ptrOn = 1;
    }, { passive: true });
    window.addEventListener('pointerleave', function () { ptrOn = 0; }, { passive: true });
    window.addEventListener('blur', function () { ptrOn = 0; });
  }

  document.addEventListener('submit', function () { pulseAt = clock; }, true);
  document.addEventListener('click', function (e) {
    var t = e.target;
    if (t.closest && t.closest('.widget-frame') &&
      (t.tagName === 'BUTTON' || t.closest('button') || t.type === 'submit')) {
      pulseAt = clock;
    }
  }, true);
})();
