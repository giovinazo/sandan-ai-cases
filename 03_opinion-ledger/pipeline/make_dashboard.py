# -*- coding: utf-8 -*-
"""협의의견 관리대장 대시보드(엑셀 6시트) 생성.

시트: 대시보드 · 협의의견대장 · 기관·부서별 현황 · 미종결관리 · 주요협의의견 · 검증_총괄표대조
원본 총괄표 기준값은 summary.json에서 읽는다(숫자를 코드에 굳혀 쓰지 않는다).
산출 엑셀을 직접 고치지 말 것(재빌드 시 덮어씀). 고칠 것은 설정·annotations.json·코드에서.
"""
import json, re, os
from collections import Counter, OrderedDict
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule, FormulaRule, DataBarRule
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.properties import CalcProperties
from openpyxl.worksheet.properties import PageSetupProperties
import cfg
import verify
from parse_summary import parse as parse_summary, totals

PJ = cfg.C['project']
BASEDATE = PJ['base_date']
EDITION = PJ['edition']
OUT = cfg.out('ledger')

recs = json.load(open(cfg.work('records.json'), encoding='utf-8'))
major = json.load(open(cfg.work('major.json'), encoding='utf-8'))
vrows = verify.build()
summ = parse_summary()
main = [r for r in recs if r['구분'] == '본협의']
rehy = [r for r in recs if r['구분'] == '재협의']
etc = [r for r in recs if r['구분'] == '총괄표 미집계']   # 원본 상세표에는 있으나 총괄표 미집계 → 집계 제외
counted = main + rehy                                       # 집계 대상(원본 총괄표 + 재협의)

FONT = '맑은 고딕'
TEAL, TEAL_D, CREAM, INK = '2E6E64', '1F4E46', 'F5F1E8', '222222'
C_MIB, C_MIG, C_BUN, C_UI, C_JAE = 'FFC7CE', 'FFE0B2', 'FFF6C7', 'E8E8E8', 'CFE3F7'
thin = Side(style='thin', color='D9D4C7')
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
GUNS = list(cfg.GROUP_NAMES)
STATS = ['반영', '부분반영', '미반영', '의견없음', '미회신', '미기재']

wb = Workbook()
wb.calculation = CalcProperties(fullCalcOnLoad=True)


def style(c, size=9, bold=False, color=INK, fill=None, ha='center', va='center',
          wrap=False, border=True):
    c.font = Font(name=FONT, size=size, bold=bold, color=color)
    c.alignment = Alignment(horizontal=ha, vertical=va, wrap_text=wrap)
    if fill:
        c.fill = PatternFill('solid', fgColor=fill)
    if border:
        c.border = BORDER
    return c


def header(ws, row, col, labels, widths=None):
    for j, h in enumerate(labels):
        style(ws.cell(row, col + j, h), bold=True, color='FFFFFF', fill=TEAL_D, wrap=True)
    if widths:
        for j, w in enumerate(widths):
            ws.column_dimensions[get_column_letter(col + j)].width = w


# ═════════════ 시트1: 대시보드(자리만 선점) ═════════════
d = wb.active
d.title = '대시보드'

# ═════════════ 시트2: 협의의견대장 ═════════════
DATA = '협의의견대장'
ws = wb.create_sheet(DATA)
COLS = ['연번', '구분', '기관군', '관계기관', '소관부서', '팀', '접수문서번호', '시행일자',
        '근거법령', '협의의견', '조치계획', '반영여부', '재협의', '쟁점유형', '비고', '출처페이지']
WIDTHS = [5, 7, 8, 15, 15, 12, 16, 11, 22, 50, 50, 9, 6, 12, 18, 7]
header(ws, 1, 1, COLS, WIDTHS)
for i, r in enumerate(recs, 2):
    for j, c in enumerate(COLS, 1):
        v = r.get(c, '')
        wrap = c in ('협의의견', '조치계획', '근거법령', '비고')
        ha = 'left' if wrap or c in ('관계기관', '소관부서', '팀', '접수문서번호') else 'center'
        style(ws.cell(i, j, v), ha=ha, va='top', wrap=wrap)
    ws.row_dimensions[i].height = 44
ws.freeze_panes = 'F2'
ws.sheet_view.showGridLines = False
NR = len(recs) + 1
tab = Table(displayName='협의대장', ref=f'A1:{get_column_letter(len(COLS))}{NR}')
tab.tableStyleInfo = TableStyleInfo(name='TableStyleLight8', showRowStripes=True)
ws.add_table(tab)
L_ST = get_column_letter(COLS.index('반영여부') + 1)
L_JAE = get_column_letter(COLS.index('재협의') + 1)
L_IS = get_column_letter(COLS.index('쟁점유형') + 1)
for val, col in (('미반영', C_MIB), ('미기재', C_MIG), ('부분반영', C_BUN),
                 ('의견없음', C_UI), ('미회신', C_UI)):
    ws.conditional_formatting.add(f'{L_ST}2:{L_ST}{NR}',
        CellIsRule(operator='equal', formula=[f'"{val}"'], fill=PatternFill('solid', fgColor=col)))
ws.conditional_formatting.add(f'{L_JAE}2:{L_JAE}{NR}',
    CellIsRule(operator='equal', formula=['"Y"'], fill=PatternFill('solid', fgColor=C_JAE),
               font=Font(bold=True, color='12507B')))
dv = DataValidation(type='list', formula1='"' + ','.join(STATS) + '"', allow_blank=True)
ws.add_data_validation(dv); dv.add(f'{L_ST}2:{L_ST}{NR}')
dv2 = DataValidation(type='list', formula1='"' + ','.join(sorted({r['쟁점유형'] for r in recs})) + '"',
                     allow_blank=True)
ws.add_data_validation(dv2); dv2.add(f'{L_IS}2:{L_IS}{NR}')

# ═════════════ 시트3: 기관·부서별 현황 ═════════════
ws2 = wb.create_sheet('기관·부서별 현황')
style(ws2.cell(1, 1, f'■ 관계기관·소관부서별 협의 현황  (기준일 {BASEDATE} · {EDITION})'),
      size=12, bold=True, color=TEAL_D, ha='left', border=False)
HC = ['기관군', '관계기관', '소관부서', '협의건수', '반영', '부분반영', '미반영', '의견없음',
      '미회신', '미기재', '재협의', '반영률', '주요쟁점']
HW = [9, 18, 22, 9, 7, 9, 8, 9, 8, 8, 7, 9, 14]
header(ws2, 3, 1, HC, HW)

agg = OrderedDict()
for r in main:
    k = (r['기관군'], r['관계기관'], r['소관부서'])
    a = agg.setdefault(k, dict(cnt=0, jae=0, issues=Counter(), **{s: 0 for s in STATS}))
    a['cnt'] += 1
    a[r['반영여부']] += 1
    if r['재협의'] == 'Y':
        a['jae'] += 1
    a['issues'][r['쟁점유형']] += 1
order = {g: i for i, g in enumerate(GUNS)}
rows2 = sorted(agg.items(), key=lambda kv: (order.get(kv[0][0], 9), kv[0][1], -kv[1]['cnt']))
r0 = 4
for i, ((gun, org, dept), a) in enumerate(rows2):
    rr = r0 + i
    vals = [gun, org, dept, a['cnt'], a['반영'], a['부분반영'], a['미반영'], a['의견없음'],
            a['미회신'], a['미기재'], a['jae']]
    for j, v in enumerate(vals, 1):
        style(ws2.cell(rr, j, v), ha=('left' if j in (2, 3) else 'center'))
    denom = a['cnt'] - a['미회신'] - a['의견없음']
    cell = ws2.cell(rr, 12, (a['반영'] + a['부분반영'] * 0.5) / denom if denom else None)
    cell.number_format = '0%'
    style(cell)
    style(ws2.cell(rr, 13, a['issues'].most_common(1)[0][0] if a['issues'] else ''), ha='left')
END2 = r0 + len(rows2) - 1
ws2.freeze_panes = 'A4'
ws2.sheet_view.showGridLines = False
tab2 = Table(displayName='기관부서현황', ref=f'A3:M{END2}')
tab2.tableStyleInfo = TableStyleInfo(name='TableStyleLight8', showRowStripes=True)
ws2.add_table(tab2)
ws2.conditional_formatting.add(f'D4:D{END2}',
    DataBarRule(start_type='num', start_value=0, end_type='max', color=TEAL))
for col, fill in (('G', C_MIB), ('H', C_UI), ('I', C_UI)):
    ws2.conditional_formatting.add(f'{col}4:{col}{END2}',
        CellIsRule(operator='greaterThan', formula=['0'], fill=PatternFill('solid', fgColor=fill)))
ws2.conditional_formatting.add(f'J4:J{END2}',
    CellIsRule(operator='greaterThan', formula=['0'], fill=PatternFill('solid', fgColor=C_MIG)))
ws2.conditional_formatting.add(f'K4:K{END2}',
    CellIsRule(operator='greaterThan', formula=['0'], fill=PatternFill('solid', fgColor=C_JAE)))

# ═════════════ 시트4: 미종결관리 ═════════════
ws3 = wb.create_sheet('미종결관리')
work = [r for r in counted if r['반영여부'] in ('미반영', '미기재', '미회신') or r['재협의'] == 'Y']
WC = ['연번', '구분', '기관군', '관계기관', '소관부서', '쟁점유형', '반영여부', '재협의',
      '협의의견', '조치계획', '비고']
WW = [5, 7, 8, 15, 15, 11, 9, 6, 52, 52, 18]
style(ws3.cell(1, 1, f'■ 미종결·검수·무응답 대상 {len(work)}건  (미반영 / 미기재 / 미회신 / 재협의)'),
      size=12, bold=True, color=TEAL_D, ha='left', border=False)
header(ws3, 3, 1, WC, WW)
for i, r in enumerate(work, 4):
    for j, c in enumerate(WC, 1):
        wrap = c in ('협의의견', '조치계획', '비고')
        style(ws3.cell(i, j, r.get(c, '')),
              ha=('left' if wrap or c in ('관계기관', '소관부서') else 'center'), va='top', wrap=wrap)
    ws3.row_dimensions[i].height = 44
END3 = 3 + len(work)
ws3.freeze_panes = 'A4'
ws3.sheet_view.showGridLines = False
for val, col in (('미반영', C_MIB), ('미기재', C_MIG), ('미회신', C_UI)):
    ws3.conditional_formatting.add(f'G4:G{END3}',
        CellIsRule(operator='equal', formula=[f'"{val}"'], fill=PatternFill('solid', fgColor=col)))
ws3.conditional_formatting.add(f'H4:H{END3}',
    CellIsRule(operator='equal', formula=['"Y"'], fill=PatternFill('solid', fgColor=C_JAE)))

# ═════════════ 시트5: 주요 협의의견 ═════════════
ws4 = wb.create_sheet('주요협의의견')
style(ws4.cell(1, 1, f'■ 주요 관계기관 협의의견 및 조치계획 {len(major)}건' + ('' if major else '  (주요 협의의견 요약본 미지정: paths.major_pdf)')),
      size=12, bold=True, color=TEAL_D, ha='left', border=False)
MC = ['연번', '관계기관', '소관부서', '협의의견', '조치계획', '비고', '출처페이지']
MW = [5, 16, 18, 58, 58, 20, 8]
header(ws4, 3, 1, MC, MW)
for i, m in enumerate(major, 4):
    vals = [i - 3, m['관계기관'], m['소관부서'], m['협의의견'], m['조치계획'], m['비고'], m['페이지']]
    for j, v in enumerate(vals, 1):
        wrap = j in (4, 5, 6)
        style(ws4.cell(i, j, v), ha=('left' if wrap or j in (2, 3) else 'center'), va='top', wrap=wrap)
    ws4.row_dimensions[i].height = 52
ws4.freeze_panes = 'A4'
ws4.sheet_view.showGridLines = False

# ═════════════ 시트6: 검증(총괄표 대조) ═════════════
ws5 = wb.create_sheet('검증_총괄표대조')
style(ws5.cell(1, 1, '■ 원본 총괄표 vs 대장 파싱 결과 대조'), size=12, bold=True,
      color=TEAL_D, ha='left', border=False)
style(ws5.cell(2, 1, '※ 총괄표 부서별 수치는 작성자 수기 집계값. 차이 발생분은 원본 확인 필요.'),
      size=8, color='888888', ha='left', border=False)
VC = ['기관군', '관계기관', '소관부서', '총괄표계', '대장계', '차이', '일치',
      '총괄_반영', '대장_반영', '총괄_부분반영', '대장_부분반영', '총괄_미반영', '대장_미반영',
      '총괄_의견없음', '대장_의견없음', '총괄_미회신', '대장_미회신', '대장_미기재', '비고']
VW = [8, 16, 20, 9, 8, 6, 6] + [10] * 11 + [14]
header(ws5, 4, 1, VC, VW)
for i, r in enumerate(vrows, 5):
    for j, c in enumerate(VC, 1):
        style(ws5.cell(i, j, r.get(c)), ha=('left' if j in (2, 3, 19) else 'center'))
END5 = 4 + len(vrows)
ws5.freeze_panes = 'A5'
ws5.sheet_view.showGridLines = False
ws5.conditional_formatting.add(f'G5:G{END5}',
    CellIsRule(operator='equal', formula=['"✗"'], fill=PatternFill('solid', fgColor=C_MIB)))

# ═════════════ 대시보드 채우기 ═════════════
d.sheet_view.showGridLines = False
d.column_dimensions['A'].width = 3
for col in 'BCDEFGHIJ':
    d.column_dimensions[col].width = 14
for col in 'LMNO':
    d.column_dimensions[col].width = 15
d.column_dimensions['K'].width = 3
style(d.cell(2, 2, f"{PJ['name']}  관계기관 협의의견 관리 대시보드"),
      size=16, bold=True, color=TEAL_D, ha='left', border=False)
style(d.cell(3, 2, f"기준일 {BASEDATE} · 원본 {EDITION}(협의기간 {PJ['period_start']}~) · {len(summ)}개 기관·부서 · "
                   f'집계 단위는 원본 총괄표와 동일(검토의견 건수 / 미회신은 부서 수)'),
      size=9, color='777777', ha='left', border=False)

DS = f"'{DATA}'"

# ── 원본 총괄표(1~2쪽) 기준값 ──────────────────────────────
SRC = totals(summ)                                   # 원본 총괄표 계행(검토의견 건수·미회신 부서 수)
SRC_RE = cfg.C['summary'].get('rehyeobui_expected') or {}   # 재협의 기준값(원본에 따로 적힌 경우만, 없으면 대조 생략)
op_main = [r for r in main if r['반영여부'] != '미회신']      # 검토의견(회신분)
no_main = [r for r in main if r['반영여부'] == '미회신']      # 미회신 부서


def kpi(row, col, label, value, color, note=''):
    style(d.cell(row, col, label), size=9, color='666666', fill=CREAM, border=False)
    style(d.cell(row + 1, col, value), size=22, bold=True, color=color, fill=CREAM, border=False)
    style(d.cell(row + 2, col, note), size=8, color='999999', fill=CREAM, border=False)


n_ban = sum(1 for r in main if r['반영여부'] == '반영')
n_open = sum(1 for r in counted if r['반영여부'] in ('미반영', '미기재') or r['재협의'] == 'Y')
kpi(5, 2, '검토의견 (본협의)', len(op_main), TEAL, f'원본 총괄표 {SRC["계"]}건')
kpi(5, 4, '반영', n_ban, '2E6E64', f'원본 {SRC["반영"]}건 · 반영률 {n_ban/len(op_main):.1%}')
kpi(5, 6, '미회신 부서', len(no_main), 'B9770E', f'원본 {SRC["미회신"]}개 부서')
kpi(5, 8, '재협의', len(rehy), '12507B', '2차 이상 협의 · 본협의표 통합분')
kpi(5, 10, '미종결', n_open, 'C0392B', '미반영·미기재·재협의')

# [표0] 원본 총괄표 대조
r0d = 9
style(d.cell(r0d, 2, '[표0] 원본 총괄표 대조  (대장 수치가 원본과 일치하는지 확인용)'),
      size=11, bold=True, color=TEAL_D, ha='left', border=False)
r0d += 1
for j, h in enumerate(['구분', '원본 총괄표', '대장', '차이', '차이 사유']):
    style(d.cell(r0d, 2 + j, h), bold=True, color='FFFFFF', fill=TEAL)
cmp_rows = [
    ('본협의 검토의견 계', SRC['계'], len(op_main), ''),
    ('  ㅇ 반영', SRC['반영'], sum(1 for r in op_main if r['반영여부'] == '반영'), ''),
    ('  ㅇ 부분반영', SRC['부분반영'], sum(1 for r in op_main if r['반영여부'] == '부분반영'), ''),
    ('  ㅇ 미반영', SRC['미반영'], sum(1 for r in op_main if r['반영여부'] == '미반영'), ''),
    ('  ㅇ 의견없음', SRC['의견없음'], sum(1 for r in op_main if r['반영여부'] == '의견없음'), ''),
    ('  ㅇ 미기재', 0, sum(1 for r in op_main if r['반영여부'] == '미기재'), ''),
    ('(참고) 총괄표 미집계 행', 0, len(etc),
     '원본 상세표에는 있으나 총괄표가 세지 않은 행(' + '·'.join(f"{r['소관부서']} {r['연번']}" for r in etc) +
     '). 구분란 「총괄표 미집계」로 두고 집계 제외'),
    ('본협의 미회신 부서', SRC['미회신'], len(no_main), ''),
]
if SRC_RE:
    cmp_rows += [
        ('재협의', SRC_RE.get('계', 0), len(rehy), '본협의표에 (2차협의) 표기로 통합된 건'),
        ('  ㅇ 반영', SRC_RE.get('반영', 0), sum(1 for r in rehy if r['반영여부'] == '반영'), ''),
        ('  ㅇ 의견없음', SRC_RE.get('의견없음', 0), sum(1 for r in rehy if r['반영여부'] == '의견없음'), ''),
    ]
for i, (lab, a, b, why) in enumerate(cmp_rows):
    rr = r0d + 1 + i
    style(d.cell(rr, 2, lab), ha='left', bold=not lab.startswith(' '))
    style(d.cell(rr, 3, a))
    style(d.cell(rr, 4, b), bold=(a != b), color=('C0392B' if a != b else INK))
    style(d.cell(rr, 5, (b - a) if b != a else '-'), color=('C0392B' if a != b else '999999'))
    style(d.cell(rr, 6, why), ha='left', size=8, color='888888')
CEND = r0d + len(cmp_rows)
style(d.cell(CEND + 1, 2, f"※ 집계는 원본 총괄표(검토의견 {SRC['계']}·미회신 {SRC['미회신']}개 부서)와 같다. 원본 상세표에만 있는 행은 "
                          '구분 「총괄표 미집계」로 대장에 남기되 집계에서 뺐다. 총괄표 부서행과 상세표 상태가 어긋나는 건은 대장 «비고»에 표시.'),
      size=8, color='888888', ha='left', border=False)

# [표1] 기관군 × 반영여부 (본협의)
r1 = CEND + 3
style(d.cell(r1, 2, '[표1] 기관군 × 반영여부  (본협의 · 미회신 포함)'), size=11, bold=True,
      color=TEAL_D, ha='left', border=False)
r1 += 1
L_GB = get_column_letter(COLS.index('구분') + 1)
for j, h in enumerate(['기관군'] + STATS + ['합계']):
    style(d.cell(r1, 2 + j, h), bold=True, color='FFFFFF', fill=TEAL)
for gi, g in enumerate(GUNS):
    rr = r1 + 1 + gi
    style(d.cell(rr, 2, g), bold=True)
    for si, s in enumerate(STATS):
        cl = get_column_letter(3 + si)
        d.cell(rr, 3 + si).value = (f'=COUNTIFS({DS}!$C:$C,$B{rr},{DS}!${L_ST}:${L_ST},{cl}${r1},'
                                    f'{DS}!${L_GB}:${L_GB},"본협의")')
        style(d.cell(rr, 3 + si))
    tc = 3 + len(STATS)
    d.cell(rr, tc).value = f'=SUM(C{rr}:{get_column_letter(2+len(STATS))}{rr})'
    style(d.cell(rr, tc), bold=True)
sr = r1 + 1 + len(GUNS)
style(d.cell(sr, 2, '합계'), bold=True, color='FFFFFF', fill=TEAL_D)
for si in range(len(STATS) + 1):
    cl = get_column_letter(3 + si)
    d.cell(sr, 3 + si).value = f'=SUM({cl}{r1+1}:{cl}{r1+len(GUNS)})'
    style(d.cell(sr, 3 + si), bold=True, color='FFFFFF', fill=TEAL_D)
# 재협의 행
jr = sr + 1
style(d.cell(jr, 2, '재협의(통합)'), bold=True, color=TEAL_D, fill=C_JAE)
for si, s in enumerate(STATS):
    cl = get_column_letter(3 + si)
    d.cell(jr, 3 + si).value = (f'=COUNTIFS({DS}!${L_ST}:${L_ST},{cl}${r1},'
                                f'{DS}!${L_GB}:${L_GB},"재협의")')
    style(d.cell(jr, 3 + si), fill=C_JAE)
d.cell(jr, 3 + len(STATS)).value = f'=SUM(C{jr}:{get_column_letter(2+len(STATS))}{jr})'
style(d.cell(jr, 3 + len(STATS)), bold=True, fill=C_JAE)

ch = BarChart(); ch.type = 'col'; ch.grouping = 'stacked'; ch.overlap = 100
ch.title = '기관군별 반영여부(본협의)'; ch.height = 7.2; ch.width = 13
ch.add_data(Reference(d, min_col=3, max_col=2 + len(STATS), min_row=r1, max_row=r1 + len(GUNS)),
            titles_from_data=True)
ch.set_categories(Reference(d, min_col=2, min_row=r1 + 1, max_row=r1 + len(GUNS)))
ch.legend.position = 'b'
d.add_chart(ch, f'B{jr+2}')

# [표2] 쟁점유형별
issue_ct = Counter(r['쟁점유형'] for r in counted).most_common()
ir, ic = 9, 12
style(d.cell(ir, ic, '[표2] 쟁점유형별 건수'), size=11, bold=True, color=TEAL_D, ha='left', border=False)
ir += 1
for j, h in enumerate(['쟁점유형', '건수']):
    style(d.cell(ir, ic + j, h), bold=True, color='FFFFFF', fill=TEAL)
for k, (name, cnt) in enumerate(issue_ct):
    style(d.cell(ir + 1 + k, ic, name), ha='left')
    style(d.cell(ir + 1 + k, ic + 1, cnt))
pie = PieChart(); pie.title = '쟁점유형 분포'; pie.height = 8.5; pie.width = 12
pie.add_data(Reference(d, min_col=ic + 1, min_row=ir, max_row=ir + len(issue_ct)), titles_from_data=True)
pie.set_categories(Reference(d, min_col=ic, min_row=ir + 1, max_row=ir + len(issue_ct)))
d.add_chart(pie, f'{get_column_letter(ic)}{ir+len(issue_ct)+2}')

# [표3] 관계기관별 현황 (관계기관명·소관부서명 표시)
gr = jr + 18
style(d.cell(gr, 2, '[표3] 관계기관별 협의 현황  (소관부서 상세는 «기관·부서별 현황» 시트)'),
      size=11, bold=True, color=TEAL_D, ha='left', border=False)
gr += 1
for j, h in enumerate(['기관군', '관계기관', '소관부서 수', '협의건수', '반영', '미반영',
                       '의견없음', '미회신', '재협의']):
    style(d.cell(gr, 2 + j, h), bold=True, color='FFFFFF', fill=TEAL)
orgagg = OrderedDict()
for r in main:
    k = (r['기관군'], r['관계기관'])
    a = orgagg.setdefault(k, dict(depts=set(), cnt=0, jae=0, **{s: 0 for s in STATS}))
    a['depts'].add(r['소관부서']); a['cnt'] += 1; a[r['반영여부']] += 1
    if r['재협의'] == 'Y':
        a['jae'] += 1
for i, ((gun, org), a) in enumerate(sorted(orgagg.items(),
                                           key=lambda kv: (order.get(kv[0][0], 9), -kv[1]['cnt']))):
    rr = gr + 1 + i
    for j, v in enumerate([gun, org, len(a['depts']), a['cnt'], a['반영'], a['미반영'],
                           a['의견없음'], a['미회신'], a['jae']], 2):
        style(d.cell(rr, j, v), ha=('left' if j == 3 else 'center'),
              color=('C0392B' if j == 7 and v else INK), bold=bool(j == 7 and v))
GEND = gr + len(orgagg)
style(d.cell(GEND + 2, 2, '※ 반영여부·쟁점유형은 대장 시트에서 드롭다운 수정 가능. '
                          '원본 총괄표와의 대조 결과는 «검증_총괄표대조» 시트.'),
      size=8, color='888888', ha='left', border=False)
style(d.cell(GEND + 3, 2, f"※ 출처: {PJ['source_title']}"),
      size=8, color='888888', ha='left', border=False)

d.page_setup.orientation = 'landscape'
d.page_setup.fitToWidth = 1; d.page_setup.fitToHeight = 1
d.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
d.print_area = f'A1:R{GEND+4}'

wb.move_sheet('대시보드', -wb.sheetnames.index('대시보드'))
wb.save(OUT)
print('저장:', OUT.relative_to(cfg.ROOT))
print('시트:', wb.sheetnames)
print(f'대장 {len(recs)}행 (본협의 {len(main)} + 재협의 {len(rehy)} + 총괄표 미집계 {len(etc)}) / '
      f'기관·부서 {len(rows2)} / 미종결 {len(work)} / 주요 {len(major)}')
