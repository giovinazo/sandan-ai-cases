#!/usr/bin/env python3
"""입체지도에 얹는 **측정 도구**와 **설명 탭** (build_3d.py 가 불러 쓴다)

  ㅇ 건물·높이·면적·거리 측정 + 측정 목록·CSV 저장 + 근거 설명 탭(네 쪽)
  ㅇ 자료는 `{data_dir}/지장물.json`(건물 윤곽과 미리 잰 치수, 좌표는 평면직각좌표). 없으면
    측정 도구는 윤곽 격자 어림만으로 돈다(화면에 그렇게 적는다)
    지장물.json 모양: {"지장물": [{"c":[E,N], "p":[[E,N],...], "면적", "긴변", "짧은변", "방위",
                                  "처마", "용마루", "부피", "물건"?, "구조"?, "지번"?, "조서면적"?, "구역내"?}]}
  ㅇ ⚠ 화면 좌표는 웹메르카토르라 실제보다 크다. 길이·넓이는 `D.tm2s` 2차식을
    **뉴턴법으로 되돌려** 평면직각좌표에서 잰다. 도면·조서와 같은 기준이다
  ㅇ ⚠ 여기서 쓰는 이름(`D`·`HS`·`MPP`·`W`·`H`·`wm`·`hm`·`mesh`·`rayc`·`ex`·`dist`·
    `isBld`·`hAt`·`render`)은 모두 build_3d.py 본문 스크립트의 것이다. 이름이 바뀌면 같이 고칠 것
  ㅇ 점검용 손잡이: 주소 끝에 `#mstest` 를 붙여 열면 window.MSTEST 로 값을 확인할 수 있다
"""
import json
import os


def obstacle_json(data_dir):
    """{data_dir}/지장물.json 을 그대로 실어 보낸다(없으면 빈 껍데기)"""
    p = os.path.join(data_dir, "지장물.json")
    if not os.path.exists(p):
        print("  (지장물.json 없음. 측정 ｢건물｣ 은 격자 어림으로만 돕니다)")
        return '{"지장물":[]}'
    s = open(p, encoding="utf-8").read().strip()
    print(f"  건물 윤곽(지장물) {len(json.loads(s)['지장물'])}개 실었습니다")
    return s


BLOCK = r"""
<script>window.MSDATA=__MSDATA__;</script>
<style>
#msBox{position:fixed;left:14px;bottom:14px;z-index:12;background:#1b1f24f2;color:#eef2f5;
  border:1px solid #333a41;border-radius:12px;padding:10px 12px;min-width:236px;max-width:330px;
  max-height:40vh;overflow:auto;display:none}
#msBox .t{color:#9aa4ad;font-size:11px;padding-right:20px}
#msBox .v{font-size:19px;font-variant-numeric:tabular-nums;color:#00d0a4;margin:2px 0 4px}
#msBox .s{font-size:12px;font-variant-numeric:tabular-nums;line-height:1.5}
#msBox .hint{color:#7e888f;font-size:11px;margin-top:7px;border-top:1px solid #333a41;padding-top:6px}
#msBox a{color:#00d0a4}
#msBoxX{position:absolute;right:7px;top:7px;padding:1px 8px 3px;font-size:15px;line-height:1.1;
  border-radius:7px;color:#9aa4ad}
#msBoxX:hover{background:#3a424a;color:#eef2f5}
#msList{position:fixed;left:14px;bottom:14px;z-index:13;background:#1b1f24f7;color:#eef2f5;
  border:1px solid #333a41;border-radius:12px;max-height:52vh;width:440px;display:none;
  flex-direction:column;overflow:hidden}
#msList .hd{padding:8px 10px;border-bottom:1px solid #333a41;display:flex;gap:6px;align-items:center}
#msList .hd b{flex:1;font-size:13px}
#msList .bd{overflow:auto}
#msList table{width:100%;border-collapse:collapse;font-size:11.5px}
#msList th{position:sticky;top:0;background:#22272d;padding:5px 7px;text-align:left;white-space:nowrap;
  color:#9aa4ad;font-weight:600}
#msList td{padding:5px 7px;border-bottom:1px solid #262c33;white-space:nowrap}
#msList td.n{text-align:right;font-variant-numeric:tabular-nums}
#msList .none{padding:14px 12px;color:#7e888f;font-size:12px}
#msHelp{position:fixed;right:12px;top:44px;z-index:14;width:min(540px,48vw);
  max-height:calc(100vh - 78px);background:#1b1f24f7;color:#eef2f5;border:1px solid #333a41;
  border-radius:12px;display:none;flex-direction:column;overflow:hidden}
#msHelp .hd{padding:9px 12px;border-bottom:1px solid #333a41;display:flex;gap:8px;align-items:center}
#msHelp .hd b{flex:1;font-size:13px}
#msHelp .tabs{display:flex;gap:6px;padding:9px 12px 0}
#msHelp .tabs button{font-size:12px;padding:5px 10px}
#msHelp .bd{overflow:auto;padding:10px 14px 14px;font-size:12px;line-height:1.62;color:#d6dde3}
#msHelp .bd h4{margin:14px 0 5px;font-size:12.5px;color:#00d0a4;font-weight:600}
#msHelp .bd h4:first-child{margin-top:4px}
#msHelp .bd p{margin:4px 0}
#msHelp .bd table{width:100%;border-collapse:collapse;margin:5px 0 3px;font-size:11.5px}
#msHelp .bd th{text-align:left;color:#9aa4ad;font-weight:600;padding:4px 6px;
  border-bottom:1px solid #333a41;vertical-align:top}
#msHelp .bd td{padding:4px 6px;border-bottom:1px solid #262c33;vertical-align:top}
#msHelp .bd td:first-child{color:#9aa4ad;white-space:nowrap}
#msHelp .bd .warn{color:#ffb4a2}
#msHelp .bd .ok{color:#00d0a4}
#msHelp .bd .sm{color:#7e888f;font-size:11px}
#msHelp .pane{display:none}
#msHelp .pane.on{display:block}
</style>
<div id="msBox"><button id="msBoxX" title="닫기 (Esc)">&times;</button><div id="msBoxC"></div></div>
<div id="msList"><div class="hd"><b>측정 목록</b>
  <button id="msCsv">CSV 저장</button><button id="msClr">비우기</button>
  <button id="msHide">닫기</button></div>
  <div class="bd"><table><thead><tr><th>#</th><th>종류</th><th>값</th>
  <th>덧붙임</th><th>자리(평면좌표)</th></tr></thead><tbody id="msRows"></tbody></table>
  <div class="none" id="msNone">아직 측정한 것이 없습니다. 왼쪽 ｢측정｣ 줄에서 건물·높이·면적·거리를 고르고 화면을 누르십시오.</div></div></div>
<div id="msHelp"><div class="hd"><b>측정값은 무엇을 근거로 하는가</b>
  <button id="msHelpX">닫기</button></div>
  <div class="tabs"><button class="mhT on" data-p="0">근거자료</button>
    <button class="mhT" data-p="1">측정방법</button>
    <button class="mhT" data-p="2">정확도</button>
    <button class="mhT" data-p="3">한계·주의</button></div>
  <div class="bd">

  <div class="pane on" data-p="0">
    <p>이 화면의 수치는 <b>설정에 적은 원자료</b>(정사영상·수치표면모델·지반 표고·건물 윤곽)에서 나옵니다.
      화면이 새로 만들어 낸 값이 아니라, 원자료를 다시 재고 서로 맞대어 본 값입니다.</p>
    <h4>쓰는 자료</h4>
    <table>
      <tr><th>자료</th><th>담긴 것</th><th>쓰는 곳</th></tr>
      <tr><td>정사영상</td><td>바탕 사진(타일을 이어 붙인 것)</td><td>화면 바탕</td></tr>
      <tr><td>수치표면모델(DSM)</td><td>표면 표고(나무·지붕 포함)</td><td>표면 지형 · 높이</td></tr>
      <tr><td>지반 표고</td><td>건물·나무를 뺀 땅 높이(점군 지면 점 등)</td><td>지반 지형 · 높이의 기준</td></tr>
      <tr><td>건물 윤곽(지장물.json)</td><td>닫힌 윤곽과 미리 잰 치수</td><td>｢건물｣ 단추</td></tr>
      <tr><td>조서(선택)</td><td>연면적 등</td><td>윤곽 면적과의 차이율</td></tr>
    </table>
    <h4>담지 않는 것</h4>
    <p>소유자 성명·주소·전화번호 같은 <b>개인정보는 넣지 않습니다.</b></p>
  </div>

  <div class="pane" data-p="1">
    <h4>항목별 산출 방법</h4>
    <table>
      <tr><th>항목</th><th>어떻게 냈는가</th></tr>
      <tr><td><b>위치</b></td><td>평면직각좌표(EPSG:__EPSG__). 화면 좌표는 웹메르카토르라
        위도에 따라 실제보다 크므로(북위 37도 부근 약 1.25배), 2차식을 뉴턴법으로 되돌려 평면좌표에서 읽습니다</td></tr>
      <tr><td><b>면적</b></td><td>건물 윤곽 폴리곤의 수평투영 면적.
        윤곽이 없는 자리에서만 격자로 세는 <b>어림</b>을 내고, 그때는 화면에 어림이라고 적습니다</td></tr>
      <tr><td><b>가로·세로</b></td><td>윤곽의 <b>최소외접사각형</b> 긴변·짧은변과 그 방위</td></tr>
      <tr><td><b>높이</b></td><td>표면 표고에서 기준면(윤곽 밖 둘레의 표면 높이 또는 지반 표고)을 뺀 값.
        <span class="sm">처마 = 하위 20% · 용마루 = 상위 95% · 평균고 = 산술평균</span></td></tr>
      <tr><td><b>부피</b></td><td>평균고 × 면적</td></tr>
      <tr><td><b>층수</b></td><td>용마루 ÷ 3m 를 반올림한 <b>어림</b>입니다. 실제 층수가 아닙니다</td></tr>
    </table>
    <h4>단추별로 무엇을 재는가</h4>
    <table>
      <tr><td><b>건물</b></td><td>건물 윤곽(지장물.json)을 먼저 찾습니다. 있으면 위 표의 값,
        없으면 격자 어림</td></tr>
      <tr><td><b>높이</b></td><td>누른 자리의 <b>표면 표고 - 지반 표고</b>.
        지붕이면 건물 높이, 나무면 수고입니다</td></tr>
      <tr><td><b>면적</b></td><td>찍은 꼭짓점을 평면좌표에서 신발끈 공식으로 잽니다(수평투영)</td></tr>
      <tr><td><b>거리</b></td><td>수평거리는 평면좌표, 경사거리는 표면 표고를 더해 잽니다</td></tr>
    </table>
    <p class="sm">길이·넓이를 평면직각좌표에서 재는 까닭은 <b>도면·조서와 기준을 맞추기 위함</b>입니다.
      구면으로 재면 원 사업 기준 0.126% 크게 나왔습니다.</p>
  </div>

  <div class="pane" data-p="2">
    <h4>정확도는 원자료를 따릅니다</h4>
    <p>화면은 원자료를 옮겨 담을 뿐이므로, 값의 정확도는 원자료(측량 성과)의 정확도를 넘지 못합니다.
      자기 자료로 만들었다면 다음을 직접 대조해 이 탭에 적어 두기를 권합니다.</p>
    <table>
      <tr><th>대조</th><th>방법</th></tr>
      <tr><td>표고</td><td>검사점·기준점 좌표의 성과 표고 대 화면 값(중앙 차이·RMS)</td></tr>
      <tr><td>좌표</td><td>화면의 평면좌표 대 GIS 변환 값 몇 곳</td></tr>
      <tr><td>면적</td><td>블록 하나를 둘레로 찍어 잰 값 대 조서·도면 면적</td></tr>
      <tr><td>건물 위치</td><td>윤곽 자리의 표면이 둘레보다 높은지, 윤곽을 50m 밀었을 때 신호가 사라지는지(대조군)</td></tr>
    </table>
    <p class="sm">예시자료는 가상이므로 이 대조가 뜻이 없습니다.</p>
  </div>

  <div class="pane" data-p="3">
    <h4 class="warn">비닐하우스는 ｢높이｣ 단추로 재지 마십시오</h4>
    <p><b>｢높이｣ 단추는 표면 - 지반</b>입니다. 사진측량 점군은 비닐 지붕 아래에 지면 점이 없어
      지붕이 곧 지면으로 들어가는 일이 많고, 그러면 높이가 0에 가깝게 나옵니다.
      비닐하우스는 <b>｢건물｣ 단추</b>로 재십시오.</p>
    <h4>높이 값의 성격</h4>
    <p>높이는 <b>표면모델 기준</b>입니다. 처마가 아니라 지붕 위쪽까지이고, 안테나·굴뚝·물탱크가
      섞일 수 있습니다. 지반 표고는 지면 점이 없는 곳(숲·비닐하우스 밑)을 <b>메운 값</b>일 수 있습니다.
      계획고가 없으면 <b>성토·절토 산정에는 쓸 수 없습니다.</b></p>
    <h4>기준시점</h4>
    <p>조서·도면·측량 성과의 기준일이 서로 다를 수 있습니다. 차이율이 크게 나오면 기준일부터 확인하십시오.</p>
    <h4>쓰임의 한계</h4>
    <p>여기 수치는 <b>업무 참고용</b>이며 감정평가·보상금액 산정을 대신하지 않습니다.
      근거로 쓰실 때는 원자료를 함께 제시하십시오.</p>
  </div>

  </div></div>
<script>
(function(){
/* ── 평면직각좌표 <-> 화면 ─────────────────────────────────
   화면 좌표는 웹메르카토르라 실제보다 크다(북위 37도 부근 약 1.25배).
   길이·넓이는 반드시 평면직각좌표로 되돌려 잰다(도면·조서와 같은 기준) */
const TM = D.tm2s;
function toScene(E,N){ const e=E-TM.c[0], n=N-TM.c[1], b=[1,e,n,e*e,n*n,e*n];
  let x=0,z=0; for(let i=0;i<6;i++){ x+=TM.x[i]*b[i]; z+=TM.z[i]*b[i]; } return [x,z]; }
function toTM(x,z){                     // 2차식이라 되돌리기는 뉴턴법으로(mm 안쪽에서 멎는다)
  let E=TM.c[0], N=TM.c[1];
  for(let k=0;k<14;k++){
    const p=toScene(E,N), dx=p[0]-x, dz=p[1]-z;
    if(Math.abs(dx)<1e-5 && Math.abs(dz)<1e-5) break;
    const h=0.5, px=toScene(E+h,N), py=toScene(E,N+h);
    const a=(px[0]-p[0])/h, b=(py[0]-p[0])/h, c=(px[1]-p[1])/h, d=(py[1]-p[1])/h;
    const det=a*d-b*c; if(!det) break;
    E-=( d*dx - b*dz)/det; N-=(-c*dx + a*dz)/det;
  }
  return [E,N];
}
/* 화면 한 칸이 실제 몇 m 인가(넓이는 이 값의 제곱을 곱한다) */
const SCALE=(function(){ const a=toTM(0,0), b=toTM(100,0);
  return Math.hypot(b[0]-a[0],b[1]-a[1])/100; })();
const CELL_M2 = (MPP*SCALE)*(MPP*SCALE);

/* ── 지형 값 읽기 ───────────────────────────────────────── */
function cellAt(x,z){
  const col=Math.round((x+wm/2)/MPP), row=Math.round((z+hm/2)/MPP);
  if(col<0||col>=W||row<0||row>=H) return -1;
  return row*W+col;
}
function at(x,z){
  const i=cellAt(x,z); if(i<0) return null;
  const s=HS['표면'][i]/10, g=HS['지반'][i]/10;
  const t=toTM(x,z);
  return {i:i, 표면:s, 지반:g, 높이:s-g, E:t[0], N:t[1]};
}
function pickPoint(ev){
  const r=renderer.domElement.getBoundingClientRect();
  const v=new THREE.Vector2((ev.clientX-r.left)/r.width*2-1,
                            -((ev.clientY-r.top)/r.height*2-1));
  rayc.setFromCamera(v,camera);
  const h=rayc.intersectObject(mesh,false);
  return h.length? h[0].point.clone() : null;
}

/* ── 그려 보이기 ────────────────────────────────────────── */
const grp=new THREE.Group(); grp.renderOrder=3; scene.add(grp);
function clearMarks(){ while(grp.children.length){ const o=grp.children.pop();
  scene.remove(o); if(o.geometry)o.geometry.dispose(); grp.remove(o);} }
function yOf(x,z){ const v=hAt(x,z); return v===null?0:v*ex+1.0; }
function dot(p,col){ const s=new THREE.Mesh(
    new THREE.SphereGeometry(Math.max(0.7,dist*0.004),10,8),
    new THREE.MeshBasicMaterial({color:col||0xffe14d}));
  s.position.set(p.x,yOf(p.x,p.z),p.z); s.renderOrder=3; grp.add(s); }
function poly(pts,col,close){
  const a=[];
  for(let i=0;i<pts.length-(close?0:1);i++){ const p=pts[i], q=pts[(i+1)%pts.length];
    a.push(p.x,yOf(p.x,p.z),p.z, q.x,yOf(q.x,q.z),q.z); }
  if(!a.length) return;
  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(a),3));
  const l=new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:col||0xffe14d}));
  l.renderOrder=3; grp.add(l);
}

/* ── 건물 자동 측정(어림) ──────────────────────────────────
   건물 윤곽을 비트로 담아 둔 것(BLD)을 눌린 자리에서 번져 나가며 훑는다.
   ⚠ 격자 한 칸 크기만큼 거친 어림이다. 정밀한 값은 윤곽 자료(지장물.json) 쪽을 먼저 쓴다 */
function floodBld(i0){
  if(typeof isBld!=='function' || !isBld(i0)) return null;
  const seen=new Uint8Array(W*H), st=[i0], cells=[];
  seen[i0]=1;
  while(st.length && cells.length<40000){
    const i=st.pop(); cells.push(i);
    const r=(i/W)|0, c=i%W;
    const nb=[[r-1,c],[r+1,c],[r,c-1],[r,c+1],[r-1,c-1],[r-1,c+1],[r+1,c-1],[r+1,c+1]];
    for(const [rr,cc] of nb){
      if(rr<0||rr>=H||cc<0||cc>=W) continue;
      const j=rr*W+cc;
      if(seen[j]||!isBld(j)) continue;
      seen[j]=1; st.push(j);
    }
  }
  const hs=cells.map(i=>(HS['표면'][i]-HS['지반'][i])/10).sort((a,b)=>a-b);
  const q=p=>hs[Math.min(hs.length-1,Math.max(0,Math.round((hs.length-1)*p)))];
  let minc=1e9,maxc=-1e9,minr=1e9,maxr=-1e9;
  cells.forEach(i=>{ const r=(i/W)|0, c=i%W;
    if(c<minc)minc=c; if(c>maxc)maxc=c; if(r<minr)minr=r; if(r>maxr)maxr=r; });
  return {칸:cells.length, 면적:cells.length*CELL_M2,
          처마:q(0.2), 용마루:q(0.95), 평균:hs.reduce((s,v)=>s+v,0)/hs.length,
          가로:(maxc-minc+1)*MPP*SCALE, 세로:(maxr-minr+1)*MPP*SCALE, cells:cells};
}
function markCells(cells){
  const a=[];
  cells.forEach(i=>{ const r=(i/W)|0, c=i%W;
    const x=c*MPP-wm/2, z=r*MPP-hm/2, y=yOf(x,z)+0.4, h=MPP/2;
    a.push(x-h,y,z-h, x+h,y,z-h, x+h,y,z-h, x+h,y,z+h,
           x+h,y,z+h, x-h,y,z+h, x-h,y,z+h, x-h,y,z-h); });
  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(a),3));
  const l=new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:0x4dd0ff}));
  l.renderOrder=3; grp.add(l);
}

/* ── 건물 실측 윤곽(지장물.json) ─────────────────────────────
   격자로 세는 어림보다 이쪽이 정확하다(원 사업에서 조서·철거도면과 면적 차이 중앙 0.0~0.1%) */
const MS = window.MSDATA || {지장물:[]};
function inPoly(pp,X,Y){ let r=false;
  for(let i=0;i<pp.length;i++){ const j=(i+1)%pp.length;
    if((pp[i][1]>Y)!==(pp[j][1]>Y) &&
       X<(pp[j][0]-pp[i][0])*(Y-pp[i][1])/(pp[j][1]-pp[i][1])+pp[i][0]) r=!r; }
  return r; }
function findItem(E,N){
  for(const it of MS.지장물){
    if(Math.abs(it.c[0]-E)>140||Math.abs(it.c[1]-N)>140) continue;
    if(inPoly(it.p,E,N)) return it; }
  return null; }
function drawItem(it){
  const a=[];
  for(let i=0;i<it.p.length;i++){ const q=it.p[i], r=it.p[(i+1)%it.p.length];
    const s1=toScene(q[0],q[1]), s2=toScene(r[0],r[1]);
    const y1=yOf(s1[0],s1[1])+0.3, y2=yOf(s2[0],s2[1])+0.3;
    a.push(s1[0],y1,s1[1], s2[0],y2,s2[1]);
    a.push(s1[0],y1,s1[1], s1[0],y1+it.용마루*ex,s1[1]);          // 높이를 세워 보인다
  }
  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(a),3));
  const l=new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:0x4dd0ff}));
  l.renderOrder=3; grp.add(l); }
function showItem(it){
  drawItem(it);
  const g = (it.조서면적&&it.면적) ? (it.면적-it.조서면적)/it.조서면적*100 : null;
  const nm = it.물건 || it.종류 || '건물·구조물';
  const addr = (it.소재지||'') + (it.지번? ' '+it.지번 : '');
  say('<div class="t">'+nm+(it.구조? ' · '+it.구조 : '')+'</div>'
   +'<div class="v">'+num(it.면적,1)+' ㎡</div>'
   +'<div class="s">'+num(it.면적/3.3058,1)+'평 · '+num(it.긴변,1)+' × '+num(it.짧은변,1)
   +' m (방위 '+it.방위.toFixed(0)+'°)</div>'
   +'<div class="s">용마루 <b>'+num(it.용마루,2)+'</b> m · 처마 '+num(it.처마,2)
   +' m · 부피 '+num(it.부피,0)+' ㎥ · '+Math.max(1,Math.round(it.용마루/3))+'층 어림</div>'
   +(addr? '<div class="s">'+addr+(it.소재지추정?' <span style="color:#d0a215">(리 추정)</span>':'')
     +(it.지목? ' · 지목 '+it.지목 : '')+'</div>' : '')
   +(it.조서면적!=null
     ? '<div class="s">조서 연면적 '+num(it.조서면적,1)+' ㎡ · 차이 <b style="color:'
       +(Math.abs(g)>10?'#ff8a80':'#00d0a4')+'">'+(g>0?'+':'')+g.toFixed(1)+'%</b></div>'
     : '<div class="s" style="color:'+(it.구역내?'#ff8a80':'#7e888f')+'">'
       +(it.구역내?'사업지구 안인데 조서에 붙지 않았습니다':'사업지구 밖 · 조서에 없는 것이 정상입니다')
       +'</div>')
   +'<div class="hint">윤곽 자료의 실측값입니다(격자 어림이 아닙니다) · '
   +'<a href="#" id="msWhy1">근거</a></div>');
  addLog(nm, num(it.면적,1)+'㎡',
    '용마루 '+num(it.용마루,2)+'m · '+num(it.긴변,1)+'×'+num(it.짧은변,1)+'m'
    +(addr?' · '+addr:''), it.c[0], it.c[1]);
}

/* ── 측정 ───────────────────────────────────────────────── */
const wrap=document.getElementById('msBox');
const box=document.getElementById('msBoxC');
const panel=document.querySelector('.panel');
let mode=null, pts=[], log=[];
/* 팝업이 왼쪽 조작판을 덮지 않도록 그 위에 올려 둔다(창 크기가 바뀌면 다시 잰다) */
function place(){
  const h = panel ? panel.getBoundingClientRect().height : 0;
  const l = document.getElementById('msList');
  l.style.bottom = (h + 22) + 'px';
  const lh = (l.style.display==='flex') ? l.getBoundingClientRect().height + 8 : 0;
  wrap.style.bottom = (h + 22 + lh) + 'px';
}
addEventListener('resize', place);
function say(html){ box.innerHTML=html; wrap.style.display='block'; place(); }
function setMode(m){
  mode = (mode===m ? null : m);
  pts=[]; clearMarks(); render();
  ['msB','msH','msA','msD'].forEach(id=>{
    const b=document.getElementById(id); if(b) b.classList.remove('on'); });
  if(mode){ const b=document.getElementById({b:'msB',h:'msH',a:'msA',d:'msD'}[mode]);
    if(b) b.classList.add('on');
    say('<div class="t">'+
      {b:'건물 측정 · 누르면 면적·치수·높이가 한 번에 나옵니다',
       h:'높이 측정 · 지붕이나 나무 위를 누르십시오',
       a:'면적 측정 · 모서리를 차례로 누르고, 두 번 누르면 끝납니다',
       d:'거리 측정 · 두 점을 누르십시오. 이어 누르면 꺾은선입니다'}[mode]+'</div>');
  } else wrap.style.display='none';
  renderer.domElement.style.cursor = mode ? 'crosshair' : '';
}
function closeBox(){                     // 닫기 단추 = 팝업을 닫고 측정도 끝낸다
  pts=[]; clearMarks();
  if(mode) setMode(mode); else wrap.style.display='none';
  render();
}
function num(v,n){ return v.toLocaleString(undefined,{minimumFractionDigits:n,maximumFractionDigits:n}); }
function addLog(kind,val,extra,E,N){
  log.push({n:log.length+1, kind:kind, val:val, extra:extra||'',
            E:E==null?'':E.toFixed(1), N:N==null?'':N.toFixed(1)});
  fillLog();
}
function fillLog(){
  const tb=document.getElementById('msRows'); tb.innerHTML='';
  log.slice().reverse().forEach(r=>{
    const tr=document.createElement('tr');
    tr.innerHTML='<td class="n">'+r.n+'</td><td>'+r.kind+'</td><td class="n">'+r.val
      +'</td><td>'+r.extra+'</td><td class="n">'+(r.E?('X '+r.N+' · Y '+r.E):'')+'</td>';
    tb.appendChild(tr);
  });
  document.getElementById('msNone').style.display = log.length? 'none':'block';
  const b=document.getElementById('msN'); if(b) b.textContent='측정 '+log.length+'건';
}
function onPick(ev){
  const p=pickPoint(ev); if(!p) return;
  const a=at(p.x,p.z); if(!a) return;
  if(mode==='b'){
    clearMarks(); dot(p,0x4dd0ff);
    const it=findItem(a.E,a.N);            // 실측 윤곽이 있으면 그 값이 정확하다
    if(it){ showItem(it); render(); return; }
    const r=floodBld(a.i);
    if(!r){
      say('<div class="t">건물이 아닌 자리입니다</div>'
        +'<div class="s">표면 '+num(a.표면,2)+'m · 지반 '+num(a.지반,2)+'m · 위에 선 것 '
        +num(a.높이,2)+'m</div><div class="hint">건물 윤곽 안을 누르십시오</div>');
      render(); return;
    }
    markCells(r.cells);
    say('<div class="t">건물(윤곽 격자 어림)</div>'
      +'<div class="v">'+num(r.면적,1)+' ㎡</div>'
      +'<div class="s">'+num(r.면적/3.3058,1)+'평 · 테두리 '+num(r.가로,1)+' × '+num(r.세로,1)+' m</div>'
      +'<div class="s">용마루 <b>'+num(r.용마루,2)+'</b> m · 처마 '+num(r.처마,2)
      +' m · 평균 '+num(r.평균,2)+' m</div>'
      +'<div class="s">부피 어림 '+num(r.평균*r.면적,0)+' ㎥ · 층수 어림 '
      +Math.max(1,Math.round(r.용마루/3))+'층</div>'
      +'<div class="hint">격자 '+r.칸+'칸('+num(MPP*SCALE,1)+'m)으로 센 <b>어림</b>입니다 · '
      +'<a href="#" id="msWhy2">근거</a></div>');
    addLog('건물', num(r.면적,1)+'㎡',
           '용마루 '+num(r.용마루,2)+'m · 처마 '+num(r.처마,2)+'m(어림)', a.E, a.N);
    render(); return;
  }
  if(mode==='h'){
    clearMarks(); dot(p);
    say('<div class="t">위에 선 것의 높이 (표면 - 지반)</div>'
      +'<div class="v">'+num(a.높이,2)+' m</div>'
      +'<div class="s">표면 표고 '+num(a.표면,2)+' m · 지반 표고 '+num(a.지반,2)+' m</div>'
      +'<div class="s">자리 X '+num(a.N,1)+' · Y '+num(a.E,1)+'</div>'
      +'<div class="hint">지붕 위를 누르면 그 건물의 높이입니다. 나무·풀에서는 수고입니다.<br>'
      +'<b>비닐하우스는 이 단추로 재면 안 됩니다</b> · <a href="#" id="msWhy3">까닭</a></div>');
    addLog('높이', num(a.높이,2)+'m',
           '표면 '+num(a.표면,2)+' / 지반 '+num(a.지반,2), a.E, a.N);
    render(); return;
  }
  pts.push(p);
  clearMarks(); pts.forEach(q=>dot(q));
  poly(pts,0xffe14d, mode==='a'&&pts.length>2);
  if(mode==='d'&&pts.length>=2){
    let flat=0, slope=0;
    for(let i=1;i<pts.length;i++){
      const A=at(pts[i-1].x,pts[i-1].z), B=at(pts[i].x,pts[i].z);
      const dh=Math.hypot(B.E-A.E, B.N-A.N);
      flat+=dh; slope+=Math.hypot(dh, B.표면-A.표면);
    }
    const A=at(pts[0].x,pts[0].z), B=at(pts[pts.length-1].x,pts[pts.length-1].z);
    say('<div class="t">수평거리 (평면직각좌표)</div>'
      +'<div class="v">'+num(flat,2)+' m</div>'
      +'<div class="s">경사거리 '+num(slope,2)+' m · 고저차 '
      +(B.표면-A.표면>=0?'+':'')+num(B.표면-A.표면,2)+' m</div>'
      +'<div class="hint">이어 누르면 꺾은선입니다 · Esc 로 지웁니다</div>');
  }
  if(mode==='a'&&pts.length>=3){
    const t=pts.map(q=>at(q.x,q.z));
    let ar=0, per=0;
    for(let i=0;i<t.length;i++){ const j=(i+1)%t.length;
      ar += t[i].E*t[j].N - t[j].E*t[i].N;
      per += Math.hypot(t[j].E-t[i].E, t[j].N-t[i].N); }
    ar=Math.abs(ar)/2;
    const hs=t.map(v=>v.높이);
    say('<div class="t">넓이 (평면직각좌표·수평투영)</div>'
      +'<div class="v">'+num(ar,1)+' ㎡</div>'
      +'<div class="s">'+num(ar/3.3058,1)+' 평 · 둘레 '+num(per,1)+' m · 꼭짓점 '+t.length+'</div>'
      +'<div class="s">꼭짓점 높이 '+num(Math.min.apply(null,hs),2)+' ~ '
      +num(Math.max.apply(null,hs),2)+' m</div>'
      +'<div class="hint">두 번 누르면 끝냅니다 · Esc 로 지웁니다</div>');
  }
  render();
}
renderer.domElement.addEventListener('dblclick', ev=>{
  if(mode!=='a'||pts.length<3) return;
  const t=pts.map(q=>at(q.x,q.z));
  let ar=0; for(let i=0;i<t.length;i++){ const j=(i+1)%t.length;
    ar += t[i].E*t[j].N - t[j].E*t[i].N; }
  ar=Math.abs(ar)/2;
  addLog('면적', num(ar,1)+'㎡', '꼭짓점 '+t.length, t[0].E, t[0].N);
  pts=[];
});
/* 끌기와 누르기를 가른다(5px 넘게 움직이면 화면을 옮긴 것으로 본다) */
let dn=null;
renderer.domElement.addEventListener('pointerdown', e=>{
  if(!mode||e.button!==0) return; dn={x:e.clientX,y:e.clientY};
}, true);
renderer.domElement.addEventListener('pointerup', e=>{
  if(!mode||!dn||e.button!==0){ dn=null; return; }
  const moved=Math.abs(e.clientX-dn.x)+Math.abs(e.clientY-dn.y); dn=null;
  if(moved<5) onPick(e);
}, true);
addEventListener('keydown', e=>{
  if(e.key==='Escape'){
    const hp=document.getElementById('msHelp');
    if(hp.style.display==='flex'){ hp.style.display='none'; return; }
    closeBox();
  }
  if(e.key==='Backspace'&&pts.length){ pts.pop(); clearMarks();
    pts.forEach(q=>dot(q)); poly(pts,0xffe14d,false); render(); }
});

/* ── 단추 잇기 ──────────────────────────────────────────── */
document.getElementById('msB').onclick=()=>setMode('b');
document.getElementById('msH').onclick=()=>setMode('h');
document.getElementById('msA').onclick=()=>setMode('a');
document.getElementById('msD').onclick=()=>setMode('d');
document.getElementById('msBoxX').onclick=closeBox;
const lst=document.getElementById('msList');
document.getElementById('msL').onclick=()=>{
  lst.style.display = lst.style.display==='flex' ? 'none' : 'flex'; place(); fillLog(); };
document.getElementById('msHide').onclick=()=>{ lst.style.display='none'; };
document.getElementById('msClr').onclick=()=>{ log=[]; fillLog(); };
document.getElementById('msCsv').onclick=()=>{
  if(!log.length){ alert('저장할 측정값이 없습니다'); return; }
  const esc=v=>'"'+String(v).replace(/"/g,'""')+'"';
  const head=['번호','종류','값','덧붙임','X(평면좌표)','Y(평면좌표)'];
  const body=log.map(r=>[r.n,r.kind,r.val,r.extra,r.N,r.E].map(esc).join(','));
  const b=new Blob(['﻿'+head.map(esc).join(',')+'\n'+body.join('\n')],
    {type:'text/csv;charset=utf-8'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(b);
  a.download='측정_'+log.length+'건.csv'; document.body.appendChild(a); a.click();
  setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},1200);
};
/* ── 설명 탭 ────────────────────────────────────────────── */
const help=document.getElementById('msHelp');
function openHelp(p){
  help.style.display='flex';
  if(p!=null) showPane(p);
}
function showPane(p){
  help.querySelectorAll('.mhT').forEach(b=>b.classList.toggle('on', b.dataset.p===String(p)));
  help.querySelectorAll('.pane').forEach(d=>d.classList.toggle('on', d.dataset.p===String(p)));
  help.querySelector('.bd').scrollTop=0;
}
help.querySelectorAll('.mhT').forEach(b=>{ b.onclick=()=>showPane(b.dataset.p); });
document.getElementById('msHelpX').onclick=()=>{ help.style.display='none'; };
document.getElementById('msHelpBtn').onclick=()=>{
  help.style.display = help.style.display==='flex' ? 'none' : 'flex'; };
/* 팝업 안의 ｢근거｣ 글씨를 누르면 해당 탭이 열린다 */
wrap.addEventListener('click', e=>{
  const id=e.target && e.target.id;
  if(id==='msWhy1'||id==='msWhy2'){ e.preventDefault(); openHelp(1); }
  if(id==='msWhy3'){ e.preventDefault(); openHelp(3); }
});
place(); fillLog();
/* 점검용 손잡이. 주소 끝에 #mstest 를 붙였을 때만 열린다(평소에는 없다).
   웹지엘 화면은 갈무리가 안 되므로, 값이 맞는지는 이쪽으로 확인한다 */
if(location.hash==='#mstest')
  window.MSTEST={findItem:findItem, toTM:toTM, toScene:toScene, SCALE:SCALE,
                 at:at, setMode:setMode, showItem:showItem, log:()=>log, data:MS};
console.log('MEASURE ready · scale='+SCALE.toFixed(6)+' cell='+(MPP*SCALE).toFixed(3)
  +'m · 지장물 '+MS.지장물.length+'개');
})();
</script>
"""


def payload(data_dir, epsg=5186):
    """build_3d.py 가 `<!--__MEASURE__-->` 자리에 끼워 넣을 덩어리"""
    return BLOCK.replace("__MSDATA__", obstacle_json(data_dir)).replace("__EPSG__", str(epsg))
