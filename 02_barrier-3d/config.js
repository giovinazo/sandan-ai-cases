/*
 * 방음벽 폐쇄감 검토 모델 설정 (모든 수치는 가상 예시값)
 * ------------------------------------------------------------
 * 자기 사업에 맞게 이 파일의 숫자만 고치면 됩니다. 단위는 m.
 * 좌표계: 원점 = 검토 구역 남서 모서리, X = 동쪽, Y = 북쪽, Z = 위.
 * 방음벽은 ㄱ자(북측 팔 + 동측 팔)로 가정합니다.
 * 수정 후: index.html은 로컬 서버로 열고, 오프라인 단일 파일은 build_offline.py로 다시 만듭니다.
 */
window.BARRIER_CONFIG = {
  projectName: '예시 산업단지',          // 화면 제목에 표시할 사업명
  latitudeDeg: 36.5,                    // 위도(태양 고도 계산용)

  wall: {
    heights: [15, 12, 8, 4, 0],         // 비교할 높이 대안(0 = 미설치)
    defaultHeight: 15,                  // 처음 열 때 높이
    northArmLength: 200,                // 북측 팔 연장 (X 0 → 이 값)
    eastArmLength: 50,                  // 동측 팔 연장 (북측 팔 동쪽 끝에서 남쪽으로)
    postSpacing: 4,                     // 지주 간격
    transmittance: 70,                  // 투명판 투과율 기본값(%)
    defaultPreset: 'T7'                 // 기본 유형(T1~T10, 화면에서 바꿀 수 있음)
  },

  roads: {
    north: { width: 25, lanes: 4 },     // 벽이 면하는 북측 도로(너머는 구역 밖 농경지)
    east:  { width: 20, lanes: 3 },     // 동측 팔이 면하는 남북 도로
    local: { width: 10, lanes: 2 },     // 구역 안 소로(남측·중간·동측)
    sidewalk: 3                         // 편측 보도 폭
  },

  site: {
    depth: 110,                         // 남측 경계에서 벽(북측 필지 경계선)까지 거리
    villaZoneWidth: 96,                 // 서쪽 끝 근린생활 용지 폭(빌라 배치 구간)
    setback: 3                          // 벽(필지 경계)에서 건물 외벽까지 이격
  },

  villa: {                              // 벽 바로 뒤 건물(창 시야 검토 대상)
    floors: 5,                          // 층수(필로티 포함)
    floorHeight: 3.3,                   // 층고(층별 시야 환산에도 사용)
    piloti: true,                       // 1층 필로티 여부
    footprintW: 12,                     // 동서 폭
    footprintD: 14,                     // 남북 깊이
    gap: 3,                             // 동 사이 간격
    parapet: 1.2                        // 옥상 난간 높이
  },

  office:   { floors: 7, floorHeight: 4.0 },                        // 벽 뒤 업무 용지 건물
  research: { floors: 5, floorHeight: 4.0, blockWidth: 70 },        // 동측 도로 건너편 건물

  floorAnalysis: {
    eyeHeight: 1.5,                     // 바닥에서 눈높이
    maxFloor: 8,                        // 표에 보일 최고 층
    noiseByFloor: { 1: 47.2, 5: 55.0, 6: 59.8 }   // 선택: 층별 예측 소음 dB(A). 가상값. 없으면 {}
  },

  // 화면 ｢가정값·근거｣ 창에 보일 근거 목록. 자기 사업 문서명으로 바꿔 적습니다.
  sources: [
    '방음벽 제원·배치: (사업) 환경영향평가서 소음 저감방안 표·그림 번호',
    '도로 폭원: (사업) 실시설계 도로표준횡단면도',
    '용지 배치·치수: (사업) 토지이용계획도 또는 교통영향평가 개선안도 축척 실측',
    '건축한계선: (사업) 지구단위계획 시행지침'
  ]
};
