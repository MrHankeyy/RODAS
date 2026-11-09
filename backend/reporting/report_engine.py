"""Versioned, source-grounded reports. No fitting or optimization occurs here."""
import base64
import copy
import hashlib
import html
import io
import json
import math
import uuid
from datetime import datetime, timezone
from dataclasses import asdict
from backend.infrastructure import file_io
from backend.services.project_service import ProjectService
from backend.domain.models import factor_title
from backend.reporting.math_format import PLOT_STYLE, formula_html, rich_text


def serializable(value):
    if isinstance(value,dict):
        return {str(k):serializable(v) for k,v in value.items() if not callable(v)}
    if isinstance(value,(list,tuple)):return [serializable(v) for v in value]
    if hasattr(value,'tolist'):return serializable(value.tolist())
    if isinstance(value,float) and not math.isfinite(value):
        return '+∞' if value==float('inf') else '-∞' if value==float('-inf') else None
    if value is None or isinstance(value,(str,int,float,bool)):return value
    raise TypeError(f'报告不支持的数据类型：{type(value).__name__}')


def inputs(project):
    return serializable({'factors':[asdict(f) for f in project.factors],
        'responses':[asdict(r) for r in project.responses], 'method':project.design_method,
        'design_params':project.design_params,'matrix':project.doe_matrix,'surrogate_config':project.surrogate_config})


def _factor_rows(factors, task_type='robust'):
    rows = []
    for factor in factors:
        p1, p2 = factor.get('param1'), factor.get('param2')
        if factor.get('uncertainty') == '概率' and p2 not in (None, ''):
            sigma = math.sqrt(float(p2))
            if factor.get('distribution') == '均匀分布':
                half = math.sqrt(3) * sigma
                p1, p2 = float(p1) - half, float(p1) + half
            else:
                p2 = sigma
        rows.append({'模型输入' if task_type=='robust' else '因子':factor.get('name'),
                     '来源':factor_title(factor.get('source'),task_type),
                     '不确定性':factor.get('uncertainty'),'分布':factor.get('distribution'),
                     '名义下限':factor.get('nominal_lower'),'名义上限':factor.get('nominal_upper'),
                     '不确定参数1':p1,'不确定参数2':p2,'单位':factor.get('unit')})
    return rows


def fingerprint(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()


def results(project):
    return serializable({'taguchi':project.taguchi_result,
        'rsm':project.rsm_result,'surrogate':project.surrogate_result,'workbench':project.workbench_result})


def record_operation(project,stage,status='完成',payload=None,message=''):
    source=inputs(project)
    record={'id':uuid.uuid4().hex,'time':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'stage':stage,'status':status,'message':str(message),'input_sha256':fingerprint(source),
        'input':source,'metadata':serializable(project.report_metadata),
        'payload':serializable(payload or {})}
    record['record_sha256']=fingerprint(record)
    project.report_history.append(copy.deepcopy(record))
    return record


def bundle(project):
    ProjectService.for_project(project).ensure_current()
    return {'format':'RAMS-report-archive','version':1,'created_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'metadata':serializable(project.report_metadata),'input':inputs(project),
        'results':results(project),'history':copy.deepcopy(project.report_history)}


def save_archive(data, path):
    """Atomic write; an interrupted export leaves the previous archive intact."""
    file_io.atomic_write_json(path, serializable(data))


def load_archive(path):
    data = file_io.read_json(path)
    if (not isinstance(data, dict)
            or data.get("format") != "RAMS-report-archive"
            or data.get("version") != 1):
        raise ValueError("不是支持的 RODAS 报告档案（版本 1）")
    if (not isinstance(data.get("input"), dict)
            or not isinstance(data.get("history"), list)
            or not isinstance(data.get("results"), dict)):
        raise ValueError("报告档案缺少输入、结果或操作记录")
    seen = set()
    required = (
        "id", "time", "stage", "status", "input", "input_sha256",
        "payload", "record_sha256")
    for record in data["history"]:
        if (not isinstance(record, dict)
                or not all(key in record for key in required)):
            raise ValueError("操作记录不完整")
        if (record["id"] in seen
                or fingerprint(record["input"]) != record["input_sha256"]):
            raise ValueError("操作记录编号重复或输入校验不一致")
        content = {
            key: value for key, value in record.items()
            if key != "record_sha256"}
        if fingerprint(content) != record["record_sha256"]:
            raise ValueError("操作记录内容校验不一致")
        if (not isinstance(record["input"], dict)
                or not isinstance(record["payload"], dict)):
            raise ValueError("操作记录的输入或结果格式无效")
        seen.add(record["id"])
    return data


_TERM_VALUES = {
    'RSM': '二次响应面模型', 'Kriging': '克里金模型',
    'SVR': '支持向量回归模型', 'ANN': '神经网络模型',
    'CCD': '中心复合设计', 'BBD': '博克斯–贝恩肯设计',
    'Latin Hypercube (LHS)': '拉丁超立方采样',
    '最优 LHS': '最大最小距离优化拉丁超立方采样',
    '低差异序列 SOBOL': '索博尔序列', '均匀网格抽样': '均匀网格采样',
    '稀疏配点法': '低维组合采样', '随机抽样': '随机采样',
    'Gaussian（高斯）': '高斯相关函数', '指数 Exponential': '指数相关函数',
    'Matern 3/2': '马特恩 3/2 相关函数',
    '常数（Ordinary）': '常数趋势', 'RBF 核': '径向基函数核',
    'Sigmoid 核': 'S形核', 'sigmoid': 'S形函数',
    'tanh': '双曲正切函数', 'relu': '修正线性单元',
    'multi': '帕累托前沿法', 'weighted': '加权和法',
    'constraint': '波动约束法',
}

_CONFIG_KEYS = {
    'model': '模型', 'model_params': '模型参数', 'sample_count': '样本点数',
    'doe_method': '试验设计方法', 'bounds': '试验范围', 'alpha_mode': '轴值模式',
    'alpha': '轴值', 'centers': '中心点数', 'replicates': '整表重复次数',
    'seed': '随机种子', 'randomize': '随机化', 'design': '设计类型',
    'total_runs': '试验次数', 'active_factors': '活动因子', 'base_runs': '基础试验次数',
    'diagnostic': '设计诊断', 'kind': '设计类型', 'cube_points': '立方点数',
    'axial_points': '轴点数', 'bounds_note': '范围说明',
    'correlation': '相关函数', 'trend': '趋势项', 'kernel': '核函数',
    'poly_degree': '多项式次数', 'c_min': '惩罚系数下限', 'c_max': '惩罚系数上限',
    'c_step': '惩罚系数步长', 'g_min': '核参数下限', 'g_max': '核参数上限',
    'g_step': '核参数步长', 'hidden_layers': '隐含层层数',
    'hidden_nodes': '隐含层节点数', 'activation': '激活函数',
    'learning_rate': '学习率', 'epochs': '训练代数', 'node_search': '节点搜索区间',
    'net_mode': '网络参数设置方法',
}


def _display_terms(value):
    if isinstance(value, str):
        return _TERM_VALUES.get(value, value)
    if isinstance(value, dict):
        return {_CONFIG_KEYS.get(key, key): _display_terms(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_display_terms(item) for item in value]
    return value


def fmt(value):
    if value is None:return '未提供 / 不可估计'
    if isinstance(value,bool):return '是' if value else '否'
    if isinstance(value,float):return f'{value:.6g}'
    if isinstance(value,(list,dict,tuple)):return json.dumps(serializable(_display_terms(value)),ensure_ascii=False)
    return str(_display_terms(value))


def table(title,rows):return {'type':'table','title':title,'rows':serializable(rows)}
def text(value):return {'type':'text','text':str(value)}


def build_report(data,kind='model',record_id=None,include_raw=False):
    history=data.get('history',[])
    if kind=='trial':
        record=next((r for r in history if r['id']==record_id),None)
        if record is None:raise ValueError('请选择一条试验或操作记录')
        source=record['input'];metadata=record.get('metadata',{});payload=record['payload']
        res=payload.get('results',{})
        if 'workbench' in payload:res={**res,'workbench':payload['workbench']}
        selected_history=[record];status=f"{record['stage']}：{record['status']}"
        title='试验与分析记录报告';created=record['time']
    else:
        source=data['input'];metadata=data.get('metadata',{});res=data.get('results',{})
        selected_history=history;status='当前输入版本的模型报告';title='产品鲁棒优化设计模型报告';created=data.get('created_utc','')
    sha=fingerprint(source)
    wb=res.get('workbench') or {}
    optimization=wb.get('optimization') or {}
    best=optimization.get('best') or {}
    sections=[]
    def section(key,title,blocks):sections.append({'id':key,'title':title,'blocks':blocks})
    matrix=source.get('matrix') or [];responses=source.get('responses') or [];factors=source.get('factors') or []
    method=source.get('method') or ''
    task_family='taguchi' if '田口' in method else 'robust'
    complete=[]
    for response in responses:
        name=response.get('name','')
        if not name:continue
        vals=[]
        for row in matrix:
            try:v=float(row.get(name))
            except (ValueError,TypeError):continue
            if math.isfinite(v):vals.append(v)
        complete.append({'响应':name,'有效数':len(vals),'总行数':len(matrix),'缺失或无效':len(matrix)-len(vals)})
    analysis_present=bool(wb.get('responses') or (res.get('rsm') or {}).get('fit') or
        (res.get('surrogate') or {}).get('responses') or
        (res.get('taguchi') or {}).get('response_analysis'))
    risks=['模型计算不等于工程实测确认；是否满足最终产品要求需结合独立确认试验。']
    if not analysis_present:risks.append('当前版本尚无完整分析结果，不生成“验证通过”或最优取值结论。')
    if not matrix:risks.append('尚无试验设计数据。')
    if any(r['缺失或无效'] for r in complete):risks.append('存在缺失或非有限响应，需补齐后重新分析。')
    if any(r['input_sha256']!=sha for r in history):risks.append('历史记录中存在其他输入版本，仅供追溯，不作为本版取值依据。')
    if kind=='model':
        not_passed=[r for r in history if r['input_sha256']==sha and r['status'] in ('失败','未通过','部分完成')]
        if not_passed:
            risks.append('本输入版本保留的未通过 / 失败记录：'+'；'.join(f"{r['stage']}（{r['id'][:12]}，{r['status']}）" for r in not_passed)+'。请结合后续修正与确认记录解释。')
    if best and (best.get('infeas') or 0)>0:risks.append('优化返回点违反设定约束，不可作为可行设计推荐。')
    if kind=='trial' and record['status']!='完成':risks.append(f"该记录状态为{record['status']}：{record.get('message','')}")
    for family in ('taguchi',):
        for name,error in (res.get(family) or {}).get('errors',{}).items():risks.append(f'{name}：{error}')
    if source.get('surrogate_config') and analysis_present:
        risks.append('代理模型检验使用测试集，不套用 OLS 系数显著性；训练精度不代表整个设计域的预测精度。')
    summary=[{'项目':metadata.get('project_name') or '未填写','报告类型':title,'状态':status,
        '设计方法':source.get('method') or '未设置','因子数':len(factors),'响应数':len(responses),'试验行数':len(matrix),
        '可追溯记录数':len(selected_history)}]
    section('summary','摘要与结论',[table('报告摘要',summary),text('本报告仅汇集已记录的数据与结果，不在报告页重新拟合或优化。'),
        text('当前有分析结果，工程确认状态：待确认。' if analysis_present else '当前证据不足，报告为待完善状态。')])
    section('purpose','目的与验证条件',[text(metadata.get('purpose') or '目的尚未填写。'),
        table('响应定义',[{'指标':r.get('name'),'角色':r.get('kind'),'目标特征':r.get('feature'),'下界':r.get('lower'),
        '上界':r.get('upper'),'响应鲁棒性阈值':r.get('robust_limit'),**({'目标值':r['target']} if r.get('target') else {}),'单位':r.get('unit')} for r in responses])])
    section('materials','材料、对象与输入',[text(metadata.get('materials') or '样机、材料、设备和试验环境尚未填写。'),
        table('模型输入定义' if task_family=='robust' else '因子定义',_factor_rows(factors,task_family)),
        text('设计变量的名义范围用于搜索，不确定性描述其加性偏差；不确定性参数不设名义范围，分布参数描述其实际取值。区间及均匀分布的两项参数为上下界，正态分布为均值偏移/标准差，均使用所列单位；带 % 的参数按当前设计值（标准差按当前均值）的比例取值。' if task_family=='robust' else '因子水平用于安排试验，水平统计按实际观测计算。')])
    params=source.get('design_params') or {}
    blocks=[text('设计方法：'+(source.get('method') or '未设置')),
        table('试验设计配置',[{'配置项':_CONFIG_KEYS.get(k,k),'值':v} for k,v in (params.get('meta') or params).items() if k!='groups']),
        table('响应完整性',complete)]
    if source.get('surrogate_config'):blocks.append(table('代理模型配置',[{'配置项':_CONFIG_KEYS.get(k,k),'值':v} for k,v in source['surrogate_config'].items()]))
    if optimization:blocks.append(table('优化条件',[{'鲁棒优化策略':{'multi':'帕累托前沿法','weighted':'加权和法','constraint':'波动约束法'}.get(optimization.get('mode'),optimization.get('mode')),'望性损失权重':optimization.get('weight'),
        '区间标准差换算系数':optimization.get('k_design'),'约束裕量系数':optimization.get('k_constraint'),
        '可行候选数':optimization.get('feasible_count'),'评价数':optimization.get('evaluated_count'),
        '种群数':optimization.get('population_size'),'代数':optimization.get('generations'),'随机种子':optimization.get('seed'),
        '逐变量交叉概率':optimization.get('pc'), '逐变量变异概率':optimization.get('effective_pm'),
        '变异概率设置':'自动（1/设计变量数）' if optimization.get('pm') is None else '手动设置',
        '交叉分布指数':optimization.get('eta_c'), '变异分布指数':optimization.get('eta_m')}]))
    if kind=='trial':
        blocks.append(text('操作说明：'+record.get('message','')))
        if payload.get('settings'):blocks.append(table('当时的运行设置',[{'设置':k,'值':v} for k,v in payload['settings'].items()]))
    section('methods','方法、数据与配置',blocks)
    blocks=[];charts=[]
    if wb.get('data'):blocks.append(table('描述统计',wb['data']))
    for name,item in wb.get('responses',{}).items():
        blocks += [table(f'{name} · 拟合与验证统计',item.get('summary',[])),table(f'{name} · 系数与区间',item.get('coefficients',[]))]
        blocks.extend(text(note) for note in item.get('notes',[]))
        observations=item.get('observations',[])
        if observations:
            charts.append({'kind':'prediction','title':f'{name}：预测与实测（{item.get("source","")}）',
                'x':[r['实测'] for r in observations],'y':[r['预测'] for r in observations]})
        if include_raw:blocks.append(table(f'{name} · 逐点诊断',observations))
    if not wb.get('responses'):
        for name,item in ((res.get('rsm') or {}).get('fit') or {}).items():
            blocks.append(table(f'{name} · 二次响应面模型',[{'决定系数':item.get('r2'),'调整决定系数':item.get('adj_r2'),'均方根误差':item.get('rmse'),'残差自由度':item.get('df_residual')}]))
        for name,item in (res.get('surrogate') or {}).get('responses',{}).items():
            if item.get('error'):blocks.append(text(f'{name}：{item["error"]}'));risks.append(f'{name} 训练失败：{item["error"]}');continue
            blocks.append(table(f'{name} · 测试集验证',[{'训练样本':item.get('train_samples'),'测试样本数':item.get('test_samples'),'测试集决定系数':item.get('r2_test'),'归一化平均绝对误差%':item.get('nmae_test_%')}]))
            if item.get('actual') and len(item['actual'])==len(item.get('predicted',[])):
                charts.append({'kind':'prediction','title':f'{name}：测试集预测与实测','x':item['actual'],'y':item['predicted']})
    for name,item in (res.get('taguchi') or {}).get('response_analysis',{}).items():
        blocks.append(table(f'{name} · 水平分析',[{'因子':r['factor'],'水平':r['level_value'],'均值':r['mean'],
            '平均组内标准差':r.get('std'),item.get('metric_label','指标'):r['metric'],'候选':r.get('recommended')} for r in item.get('levels',[])]))
        blocks.append(table(f'{name} · 内表观测',[{'内表组':r['inner'],'观测数':r['n'],'均值':r['mean'],'标准差':r.get('std'),'指标':r['metric'],'设置':r['settings']} for r in item.get('runs',[])]))
        blocks.append(text(item.get('note','')))
    if res.get('taguchi'):risks.append('田口候选采用主效应可加假设，必须做确认试验；不同目标有冲突时不能直接合并。')
    if wb.get('anova_text'):blocks.append(text(wb['anova_text']))
    if wb.get('validation_text'):blocks.append(text(wb['validation_text']))
    if not blocks:blocks=[text('尚无分析结果。')]
    blocks += [{'type':'chart',**c} for c in charts]
    section('results','分析结果与推论依据',blocks)
    blocks=[]
    if best:
        blocks.append(table('优化返回参数',[{'因子':k,'取值':v} for k,v in best.get('x',{}).items()]))
        blocks.append(table('优化返回点响应',best.get('responses',[])))
        blocks.append(text('模型约束判定：'+('违反约束，不能作为可行推荐。' if (best.get('infeas') or 0)>0 else '按记录的数值精度满足设定约束；需独立确认。')))
        front=optimization.get('front') or []
        if front and len(front[0].get('obj',[]))>=2:
            blocks.append({'type':'chart','kind':'pareto','title':'可行帕累托前沿：望性损失与归一化标准差',
                'x':[r['obj'][0] for r in front],'y':[r['obj'][1] for r in front]})
    for name,candidate in (res.get('taguchi') or {}).get('best_levels_by_response',{}).items():
        blocks.append(table(f'{name} · 待确认水平',[{'因子':k,'水平':v} for k,v in candidate.items()]))
    if (res.get('taguchi') or {}).get('recommendation'):blocks.append(text(res['taguchi']['recommendation']))
    for name,rows in wb.get('tolerance',{}).items():blocks.append(table(f'{name} · 局部方差贡献分析',[{'来源':r['name'],'方差':r.get('variance'),'份额%':r['share']} for r in rows]))
    if wb.get('model_formulas'):
        for name, formulas in wb['model_formulas'].items():
            blocks.append(text(name + ' · 拟合方程（编码变量）'))
            blocks.append({'type': 'formula', 'parts': formulas['equation']})
            blocks.append(text('输入编码关系：'))
            blocks.extend({'type': 'formula', 'parts': [value]} for value in formulas['coding'])
    elif wb.get('model_text'):
        blocks.append(text(wb['model_text']))
    if not blocks:blocks=[text('尚无优化方案结果。')]
    section('settings','优化方案与波动核验',blocks)
    if optimization or wb:risks.append('μ±kσ 是独立输入、对角二阶近似下的稳健带，不是预测区间，不保证概率覆盖。')
    section('risks','风险、未通过项与确认计划',[text(r) for r in dict.fromkeys(risks)]+[
        text('人工结论 / 复核意见：'+(metadata.get('conclusion') or '未填写，未自动判定工程验收通过。')),
        text('确认计划：'+(metadata.get('confirmation') or '建议对候选参数开展独立实测，复核均值、波动和约束；记录未达标原因与修正方案。'))])
    section('history','试验记录与版本追溯',[table('操作记录',[{'记录ID（前12位）':r['id'][:12],'时间UTC':r['time'].replace('T',' ').replace('+00:00',''),'阶段':r['stage'],
        '状态':r['status'],'输入版本':r['input_sha256'][:12],'适用于本版':r['input_sha256']==sha,'说明':r.get('message','')} for r in selected_history]),
        text('记录从本功能启用后开始；此前未记录的操作无法追补。完成表示计算或录入完成，不表示工程验证通过。'),
        text('输入 SHA-256：'+sha)])
    if include_raw or kind=='trial':section('appendix','附录：原始试验设计数据',[table('试验数据表与回填响应',matrix)])
    return {'title':title,'kind':kind,'record_id':record_id,'created_utc':created,'input_sha256':sha,
        'metadata':metadata,'status':status,'sections':sections,'risks':list(dict.fromkeys(risks))}


def chart_png(block):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import matplotlib
    with matplotlib.rc_context(PLOT_STYLE):
        fig=Figure(figsize=(7.2,3.3),dpi=125,layout='constrained');FigureCanvasAgg(fig);ax=fig.add_subplot()
        x,y=block['x'],block['y']
        if block['kind']=='bar':ax.bar(x,y,color='#245f9e');ax.axhline(0,color='gray',lw=.6);ax.tick_params(axis='x',rotation=25)
        else:
            ax.scatter(x,y,s=20,color='#245f9e')
            if block['kind']=='prediction':
                lo,hi=min(x+y),max(x+y);ax.plot([lo,hi],[lo,hi],'--',color='gray');ax.set(xlabel='实测',ylabel='预测')
            else:ax.set(xlabel='望性损失',ylabel='归一化标准差')
        ax.set_title(block['title'],fontsize=11);ax.grid(alpha=.2)
        out=io.BytesIO();fig.savefig(out,format='png');return out.getvalue()


def render_html(report,section_ids=None):
    esc=lambda value:rich_text(fmt(value))
    selected=set(section_ids) if section_ids is not None else None
    meta=report['metadata']
    chunks=['<!doctype html><html><head><meta charset="utf-8"/><style>body{font-family:"Microsoft YaHei",sans-serif;color:#243449;font-size:10pt;} h1{font-size:22pt;color:#17385e;} h2{font-size:15pt;color:#17385e;margin-top:24px;} h3{font-size:11pt;color:#245f9e;} table{border-collapse:collapse;width:100%;font-size:9pt;} th{background:#e7eef7;} td,th{border:1px solid #cbd5e1;padding:5px;text-align:left;} p{line-height:1.5;} .meta{color:#50657d;} </style></head><body>',
        f'<h1>{esc(report["title"])}</h1>',f'<p class="meta">项目：{esc(meta.get("project_name") or "未填写")}<br/>编制：{esc(meta.get("author") or "未填写")}<br/>时间 UTC：{esc(report["created_utc"])}<br/>输入版本：{esc(report["input_sha256"][:12])}　状态：{esc(report["status"])}</p>']
    for section in report['sections']:
        if selected is not None and section['id'] not in selected:continue
        chunks.append(f'<h2 id="{section["id"]}">{esc(section["title"])}</h2>')
        for block in section['blocks']:
            if block['type']=='text':chunks.append(f'<p>{esc(block["text"])}</p>')
            elif block['type']=='formula':
                chunks.append('<p>'+' '.join(formula_html(part) for part in block['parts'])+'</p>')
            elif block['type']=='chart':
                encoded=base64.b64encode(chart_png(block)).decode('ascii')
                chunks.append(f'<p><img width="610" height="280" src="data:image/png;base64,{encoded}" alt="{esc(block["title"])}"/></p>')
            else:
                rows=block['rows'];chunks.append(f'<h3>{esc(block["title"])}</h3>')
                if not rows:chunks.append('<p>无可用记录。</p>');continue
                keys=list(dict.fromkeys(k for row in rows for k in row))
                # Long statistical tables are split vertically into field groups, keeping the first identifier.
                groups=[keys] if len(keys)<=8 else [[keys[0]]+keys[i:i+7] for i in range(1,len(keys),7)]
                for columns in groups:
                    chunks.append('<table width="100%" cellspacing="0" cellpadding="4"><thead><tr>'+''.join(f'<th>{esc(k)}</th>' for k in columns)+'</tr></thead><tbody>')
                    for row in rows:chunks.append('<tr>'+''.join(f'<td>{esc(row.get(k))}</td>' for k in columns)+'</tr>')
                    chunks.append('</tbody></table><br/>')
    chunks.append('<p class="meta">RODAS · 可追溯分析报告 · 计算结论需按确认计划复核</p></body></html>')
    return ''.join(chunks)


def export_pdf(html_text, path):
    """Compatibility entry point; file writing lives in file_io."""
    return file_io.export_pdf(html_text, path)


def build_current_report(data):
    """Render only this calculation, without trial history or authoring workflow."""
    current = dict(data, history=[])
    report = build_report(current)
    report['title'] = '产品鲁棒优化设计结果报告'
    report['status'] = '本次计算结果'
    optimization = (data.get('results', {}).get('workbench') or {}).get('optimization') or {}
    if optimization.get('sigma_limits'):
        section = next(s for s in report['sections'] if s['id'] == 'settings')
        section['blocks'].append(table('独立波动约束（响应原单位）', optimization['best'].get('sigma_constraints', [])))
    report['sections'] = [s for s in report['sections'] if s['id'] != 'history']
    for section in report['sections']:
        if section['id'] == 'risks':
            section['title'] = '结果适用范围与确认建议'
            section['blocks'] = [b for b in section['blocks'] if not b.get('text', '').startswith('人工结论')]
        if section['id'] in ('purpose', 'materials'):
            section['blocks'] = [b for b in section['blocks'] if b['type'] != 'text' or '尚未填写' not in b.get('text', '')]
        for block in section['blocks']:
            if block['type'] == 'table':
                for row in block['rows']:
                    row.pop('可追溯记录数', None)
                    if '报告类型' in row:
                        row['报告类型'] = report['title']
                        row['状态'] = report['status']
    return report
