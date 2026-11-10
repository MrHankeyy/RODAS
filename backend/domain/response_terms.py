"""Shared response semantics for editors, results and reports."""

def limit_name(kind):
    return '约束阈值' if kind == '约束' else '目标鲁棒性阈值'


def criterion_name(kind, feature):
    mapping = ({'望大': '不小于下限', '望小': '不大于上限', '望目': '位于区间内'}
               if kind == '约束' else
               {'望大': '最大化', '望小': '最小化', '望目': '趋近目标值'})
    return mapping.get(feature, feature)
