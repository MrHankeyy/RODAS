"""Explicit numerical prediction state shared by training and task restoration."""
from dataclasses import dataclass
import numpy as np


def correlation(a, b, theta, label):
    d2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
    if label == '指数':
        return np.exp(-np.sqrt(d2) * theta)
    if label == 'Matern 3/2':
        s = np.sqrt(d2) * theta
        return (1 + s) * np.exp(-s)
    return np.exp(-d2 * theta)


def trend_matrix(values, kind):
    columns = [np.ones(len(values))]
    if '一次' in kind or '二次' in kind:
        columns.extend(values[:, j] for j in range(values.shape[1]))
    if '二次' in kind:
        columns.extend(values[:, j] ** 2 for j in range(values.shape[1]))
    return np.column_stack(columns)


@dataclass
class Predictor:
    kind: str
    state: dict

    def predict(self, values):
        x = np.asarray(values, float)
        s = self.state
        if self.kind == 'kriging':
            x = x / s['span']
            return (trend_matrix(x, s['trend']) @ s['beta']
                    + correlation(s['x'], x, s['theta'], s['correlation']).T @ s['weights'])
        if self.kind in ('svr', 'krr'):
            support = s['support']
            kernel = s['kernel']
            if kernel == 'rbf':
                distance = ((x[:, None, :] - support[None, :, :]) ** 2).sum(axis=2)
                k = np.exp(-s['gamma'] * distance)
            elif kernel == 'poly':
                k = (s['gamma'] * (x @ support.T) + s['coef0']) ** s['degree']
            elif kernel == 'sigmoid':
                k = np.tanh(s['gamma'] * (x @ support.T) + s['coef0'])
            else:
                raise ValueError('不支持的核函数：' + kernel)
            return k @ s['dual'] + s['intercept']
        if self.kind == 'ann':
            x = (x - s['x_mean']) / s['x_std']
            for i, (weights, bias) in enumerate(zip(s['weights'], s['biases'])):
                x = x @ weights + bias
                activation = s['activation'] if i < len(s['weights']) - 1 else s['out_activation']
                if activation in ('sigmoid', 'logistic'):
                    from scipy.special import expit
                    x = expit(x)
                elif activation == 'tanh':
                    x = np.tanh(x)
                elif activation == 'relu':
                    x = np.maximum(x, 0)
                elif activation == 'exp':
                    x = np.exp(x)
                elif activation != 'identity':
                    raise ValueError('不支持的激活函数：' + activation)
            return x.ravel() * s['y_std'] + s['y_mean']
        raise ValueError('不支持的模型类型：' + self.kind)

    def __call__(self, values):
        return float(self.predict(np.asarray(values, float).reshape(1, -1))[0])
