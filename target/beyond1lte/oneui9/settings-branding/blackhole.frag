// Riftroam profile black-hole scene, reused at its author's request.
// Source: profile/worker/shader-bg.mjs (COMMON + SKY + blackhole + MAIN).
// The shader runs at build time; Settings only displays the rendered frames.
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 R;uniform float T;uniform vec2 M;uniform vec3 A;uniform vec3 B;uniform vec3 C;uniform vec3 K;uniform float S;
vec2 KP;float KA;
float hash(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
float vnoise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),f.x),f.y);}
float fbm(vec2 p){float s=0.,w=.5;for(int i=0;i<5;i++){s+=w*vnoise(p);p=p*2.02+vec2(31.7,17.9);w*=.5;}return s;}
const float W=.01309;
mat2 rot(float a){float c=cos(a),s=sin(a);return mat2(c,s,-s,c);}
float fbm4(vec2 p){float s=0.,w=.5;for(int i=0;i<4;i++){s+=w*vnoise(p);p=p*2.03+vec2(17.3,9.1);w*=.5;}return s;}
vec3 stars(vec2 p,float sc,float thr,float rad,float gain,float seed,float px){
vec2 s=p*sc;vec2 g0=floor(s-.5);
float r=max(rad,px*sc*.8);
vec3 acc=vec3(0.);
for(int j=0;j<2;j++){for(int i=0;i<2;i++){
vec2 g=g0+vec2(float(i),float(j));
float h=hash(g+seed);
if(h>thr){
vec2 o=(vec2(hash(g*1.7+seed+5.3),hash(g+seed+11.9))-.5)*.56;
vec2 d=s-(g+.5+o);
float k=(h-thr)/(1.-thr);
float tw=.8+.2*sin(T*(1.3+k*2.7)+h*80.);
vec3 tint=mix(vec3(.62,.76,1.),vec3(1.,.8,.55),fract(h*37.1));
acc+=mix(tint,vec3(1.),.4)*exp(-dot(d,d)/(r*r))*(.2+.8*k*k)*tw*gain;
}}}
return acc;
}
vec3 bigStars(vec2 p,float sc,float seed){
vec2 s=p*sc;vec2 g=floor(s);
float h=hash(g+seed);
if(h<.93) return vec3(0.);
vec2 d=fract(s)-.5-(vec2(hash(g*1.3+seed+2.1),hash(g+seed+8.7))-.5)*.4;
float k=(h-.93)/.07;
float tw=.82+.18*sin(T*(1.+k*2.)+h*90.);
float q=dot(d,d);
float core=exp(-q/(.0014+.0018*k));
float halo=exp(-q/(.016+.03*k))*(.18+.5*k);
float spike=(exp(-abs(d.x)*80.)*exp(-abs(d.y)*9.)+exp(-abs(d.y)*80.)*exp(-abs(d.x)*9.))*k*k;
vec3 tint=mix(mix(vec3(.7,.8,1.),vec3(1.,.82,.6),fract(h*53.7)),vec3(1.),.35);
return tint*(core*(1.2+1.4*k)+halo*.5+spike*1.1)*tw;
}
float clickRing(vec2 uv){float kr=.95*(1.-exp(-KA*1.7));float kw=(length(uv-KP)-kr)*22.;return exp(-kw*kw)*exp(-KA*1.05)*(1.-step(8.,KA));}
float clickFlare(vec2 uv){vec2 d=uv-KP;float f=exp(-KA*2.2)*(1.-step(5.,KA));return f*(exp(-dot(d,d)*900.)*1.6+(exp(-abs(d.x)*55.)*exp(-abs(d.y)*5.5)+exp(-abs(d.y)*55.)*exp(-abs(d.x)*5.5))*.55+exp(-dot(d,d)*60.)*.25);}
const float TAU=6.2831853;
float pn(vec2 p,float per){
vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
float x0=mod(i.x,per),x1=mod(i.x+1.,per);
return mix(mix(hash(vec2(x0,i.y)),hash(vec2(x1,i.y)),f.x),mix(hash(vec2(x0,i.y+1.)),hash(vec2(x1,i.y+1.)),f.x),f.y);
}
float pfbm(vec2 p,float per){float s=0.,w=.5;for(int i=0;i<3;i++){s+=w*pn(p,per);p=p*2.+vec2(0.,13.7);per*=2.;w*=.5;}return s;}
// Birikim diski: q disk düzlemindeki konum (gölge yarıçapı = 1). rgb ışıma, a opaklık.
vec4 disc(vec2 q,float flow,float lit,float ri,float w){
float r=length(q);
if(r<ri||r>9.) return vec4(0.);
float u=(atan(q.y,q.x)-mod(flow*.62/(r*sqrt(r)),TAU))/TAU;
float n1=pfbm(vec2(u*64.,r*7.),64.);
float n2=pn(vec2(u*256.,r*30.),256.);
float n3=pn(vec2(u*512.,r*83.),512.);
float st=.08+1.1*n1*n1+.6*n2*n2+.35*n3;
float prof=pow((ri+.15)/max(r,ri+.15),1.9)*smoothstep(9.,3.,r)*smoothstep(ri,ri+w,r);
float beam=pow(clamp(1.+.7*q.x/r,.12,1.9),3.)*lit;
float tt=clamp((r-ri-.1)/6.,0.,1.);
vec3 hot=mix(vec3(1.),A,.28);
vec3 c=mix(hot,A,smoothstep(0.,.16,tt));
c=mix(c,B,smoothstep(.08,.75,tt));
c*=mix(1.,.55,smoothstep(.45,1.,tt));
float em=prof*st*beam;
return vec4(c*em*4.6,clamp(em*3.2,0.,1.));
}
vec3 scene(vec2 uv,vec2 mp){
vec2 asp=R/min(R.x,R.y);
float px=2./min(R.x,R.y);
float ring=clickRing(uv);
vec2 uv0=uv;
vec2 kd=uv-KP;
uv+=kd/(length(kd)+.001)*ring*.03;
float ratio=asp.x/asp.y;
float land=smoothstep(.85,1.35,ratio);
vec2 ctr=mix(vec2(0.,asp.y*.4),vec2(asp.x*.24,asp.y*.12),land);
float rs=mix(asp.x*.3,asp.y*.34,land);
float tilt=mix(.14,.34,land)+mp.x*.05;
float ci=.2+.05*mp.y;
vec2 p=rot(-tilt)*((uv-ctr-mp*.02)/rs);
float b=length(p);
float outside=smoothstep(.985,1.,b);
vec2 beta=p*(1.-1./max(b*b,1.0001));
vec2 bgp=ctr+rs*(rot(tilt)*beta);
float b2=b*b;
float mag=min(2.2,1./max(abs(1.-1./(b2*b2)),.3));
float flow=T+S*1.4;
vec3 sk=stars(bgp+mp*.02,150.,.984,.15,.55,21.,px);
sk+=stars(bgp+mp*.04,70.,.986,.19,.8,33.,px);
sk+=bigStars(bgp+mp*.07,9.,5.)*.8;
sk+=bigStars(bgp+mp*.1,5.,17.)*.7;
vec2 dp=rot(-.5)*(bgp-ctr);
float haze=fbm4(bgp*1.15+vec2(T*.003,3.));
float band=exp(-dp.y*dp.y*1.1);
vec3 dust=mix(C*.5,vec3(.62,.62,.78),.4)*smoothstep(.25,.8,haze)*band*.42;
dust+=C*.03*band;
vec3 col=(sk*mag+dust)*outside;
float lit=.9;
float sideBright=.55+.9*smoothstep(-1.,1.,p.x);
float pr=exp(-pow((b-1.)*70.,2.));
col+=mix(vec3(1.),A,.4)*pr*(.3*sideBright*sideBright)*step(.97,b);
col+=A*.08*exp(-(b-1.)*2.2)*smoothstep(.985,1.03,b)*sideBright;
vec4 lt=vec4(0.);
if(b>1.){
if(p.y>0.) lt=disc(vec2(beta.x,beta.y/ci),flow,lit,.8,.2)*vec4(vec3(mag*.7+.9),1.)*smoothstep(0.,.35,p.y);
else lt=disc(vec2(beta.x,-beta.y/ci),flow,lit,.8,.2)*vec4(vec3(.5),.55)*smoothstep(0.,.35,-p.y);
}
col=col*(1.-lt.a)+lt.rgb;
vec4 dd=disc(vec2(p.x,p.y/(ci*.5)),flow,lit,1.,1.3);dd.rgb*=1.5;
float vis=p.y<0.?1.:smoothstep(.98,1.04,b);
col=col*(1.-dd.a*vis)+dd.rgb*vis;
float wide=exp(-abs(p.y)*1.6)*exp(-abs(p.x)*.24);
col+=mix(A,B,.5)*.07*wide*smoothstep(.9,1.4,b);
col+=B*.035*exp(-b*.55);
col+=mix(vec3(1.),A,.3)*ring*.5+mix(vec3(1.),A,.2)*clickFlare(uv0);
vec3 o=1.-exp(-col*1.35);
o=pow(o,vec3(1.04));
float l=dot(o,vec3(.3,.59,.11));
return mix(vec3(l),o,1.2);
}
void main(){
vec2 asp=R/min(R.x,R.y);
vec2 uv=(gl_FragCoord.xy/R*2.-1.)*asp;
vec2 mp=(M*2.-1.)*asp;
KP=(K.xy*2.-1.)*asp;KA=K.z;
vec3 col=scene(uv,mp);
vec2 vv=gl_FragCoord.xy/R-.5;
col*=1.-.76*dot(vv,vv);
col+=(hash(gl_FragCoord.xy+fract(T))-.5)/120.;
gl_FragColor=vec4(clamp(col,0.,1.),1.);
}
