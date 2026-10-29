"""Versioned .rodas archives: committed state and numerical models, no pickle."""
from dataclasses import asdict, fields
from hashlib import sha256
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import uuid
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
from backend.core.predictors import Predictor
from backend.core.factors import model_factors
from backend.domain.models import ProjectData, FactorItem, ResponseItem
from backend.services.project_service import ProjectService


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')


def _model_probes(model):
    s = model.state
    if model.kind == 'kriging':
        count = len(s['span'])
    elif model.kind in ('svr', 'krr'):
        count = s['support'].shape[1]
    elif model.kind == 'ann':
        count = len(s['x_mean'])
    else:
        raise ValueError('不支持的模型类型：' + model.kind)
    return np.array([np.zeros(count), np.ones(count), np.full(count, .37)])


def _pack(project):
    service = ProjectService.for_project(project)
    service.ensure_current()
    arrays = {}

    def encode(value):
        if isinstance(value, np.ndarray):
            buffer = BytesIO()
            np.save(buffer, value, allow_pickle=False)
            name = f'arrays/{len(arrays)}.npy'
            arrays[name] = buffer.getvalue()
            return dict(type='array', name=name, sha256=sha256(arrays[name]).hexdigest())
        if isinstance(value, np.generic):
            return encode(value.item())
        if isinstance(value, Predictor):
            probes = _model_probes(value)
            output = value.predict(probes)
            if not np.isfinite(output).all():
                raise ValueError('模型预测存在非有限数，无法存档。')
            return dict(type='predictor', version=1, kind=value.kind, state=encode(value.state),
                        checks=output.tolist())
        if isinstance(value, dict):
            return dict(type='map', items=[[str(k), encode(v)] for k, v in value.items()])
        if isinstance(value, (list, tuple)):
            return [encode(v) for v in value]
        if isinstance(value, float) and not math.isfinite(value):
            return dict(type='float', value=str(value))
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise ValueError(f'任务中存在不能存档的对象：{type(value).__name__}')

    data = {f.name: getattr(project, f.name) for f in fields(ProjectData) if f.name != 'report_history'}
    data['factors'] = [asdict(f) for f in project.factors]
    data['responses'] = [asdict(r) for r in project.responses]
    document = encode(dict(project=data, models=service.model_cache))
    manifest = dict(format='RODAS', version=2, software_version='0.2', document=document,
                    input_sha256=sha256(service.input_signature().encode('utf-8')).hexdigest())
    return _json(manifest), arrays


def fingerprint(project):
    manifest, _ = _pack(project)
    return sha256(manifest).hexdigest()


def save_task(project, path):
    manifest, arrays = _pack(project)
    target = Path(path).resolve()
    temporary = target.with_name('.rodas-' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            with ZipFile(stream, 'w', compression=ZIP_DEFLATED) as archive:
                archive.writestr('task.json', manifest)
                for name, value in arrays.items():
                    archive.writestr(name, value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256(manifest).hexdigest()


def load_task(path):
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if (len(members) != len(set(archive.namelist())) or len(members) > 10000
                    or sum(m.file_size for m in members) > 1024 ** 3
                    or archive.getinfo('task.json').file_size > 64 * 1024 ** 2):
                raise ValueError('任务文件结构异常或过大。')
            manifest = json.loads(archive.read('task.json'))
            if manifest.get('format') != 'RODAS' or manifest.get('version') not in (1, 2):
                raise ValueError('不支持的任务文件格式或版本。')

            def decode(value):
                if isinstance(value, list):
                    return [decode(v) for v in value]
                if not isinstance(value, dict):
                    return value
                kind = value['type']
                if kind == 'map':
                    items = value['items']
                    return {k: decode(v) for k, v in (items.items() if isinstance(items, dict) else items)}
                if kind == 'float' and value['value'] in ('nan', 'inf', '-inf'):
                    return float(value['value'])
                if kind == 'array':
                    if not re.fullmatch(r'arrays/\d+\.npy', value['name']):
                        raise ValueError('数组路径无效。')
                    raw = archive.read(value['name'])
                    if sha256(raw).hexdigest() != value['sha256']:
                        raise ValueError('模型数组损坏。')
                    result = np.load(BytesIO(raw), allow_pickle=False)
                    if result.dtype.kind not in 'biuf':
                        raise ValueError('模型数组类型无效。')
                    return result
                if kind == 'predictor':
                    if value.get('version') != 1:
                        raise ValueError('不支持的模型存档版本。')
                    model = Predictor(value['kind'], decode(value['state']))
                    actual = model.predict(_model_probes(model))
                    if not np.isfinite(actual).all() or not np.allclose(actual, value['checks'], rtol=1e-10, atol=1e-12):
                        raise ValueError('模型预测一致性校验失败。')
                    return model
                raise ValueError('任务中存在不支持的数据类型。')

            data = decode(manifest['document'])
        values = data['project']
        values['factors'] = [FactorItem(**v) for v in values['factors']]
        values['responses'] = [ResponseItem(**v) for v in values['responses']]
        project = ProjectData(**values)
        service = ProjectService.for_project(project)
        if sha256(service.input_signature().encode('utf-8')).hexdigest() != manifest['input_sha256']:
            raise ValueError('任务输入版本校验失败。')
        service.model_cache = data['models']
        # Validate model dimensions in raw input order, without training anything.
        count = len(model_factors(project))
        for result in project.surrogate_result.get('responses', {}).values():
            predictor = result.get('predict_fn')
            if predictor is not None and (not isinstance(predictor, Predictor) or _model_probes(predictor).shape[1] != count):
                raise ValueError('预测模型与输入因子不匹配。')
        return project
    except Exception as exc:
        raise ValueError(f'无法读取任务：{exc}') from exc
