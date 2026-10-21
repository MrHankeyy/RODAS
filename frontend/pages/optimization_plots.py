"""Matplotlib rendering helpers for the optimization page."""
import math


def pareto(figure, canvas, robust):
    figure.clear()
    axes = figure.add_subplot(111)
    scatter = robust.get("front_scatter") or []
    if robust.get("mode") == "constraint" and robust.get("best"):
        constraints = robust["best"].get("sigma_constraints", [])
        names = [row["name"] for row in constraints]
        ratios = [
            row["sigma"] / row["sigma_limit"] for row in constraints]
        axes.barh(
            names, ratios,
            color=["#168064" if ratio <= 1 else "#c73545"
                   for ratio in ratios])
        axes.axvline(
            1, color="#c73545", linestyle="--", label="允许上限")
        axes.set_xlabel(r"$\sigma / \sigma_{\max}$（≤ 1 为通过）")
        axes.set_title("候选点独立波动约束核验")
        axes.legend(fontsize=8)
    elif scatter:
        axes.scatter(
            [point[0] for point in scatter],
            [point[1] for point in scatter],
            s=18, alpha=0.6, color="#17a2b8", label="可行进化解")
        front = robust.get("front") or []
        if front:
            x_values = [point["obj"][0] for point in front]
            y_values = [
                point["obj"][1] for point in front
                if len(point["obj"]) > 1]
            if len(y_values) == len(x_values):
                axes.plot(
                    x_values, y_values, "-o", color="#1d4ed8",
                    lw=1.6, label="帕累托前沿")
        knee = robust.get("knee")
        if knee and len(knee["obj"]) > 1:
            axes.scatter(
                [knee["obj"][0]], [knee["obj"][1]], s=120,
                marker="*", color="#f97316", label="Knee Point")
        best = robust.get("best")
        if best and len(best["obj"]) > 1:
            axes.scatter(
                [best["obj"][0]], [best["obj"][1]], s=60,
                marker="D", color="#16a34a", label="推荐解")
        axes.set_xlabel("均值损失（1 − 望性）")
        axes.set_ylabel(r"归一化标准差 $\sigma$")
        axes.set_title("鲁棒优化 帕累托前沿")
        axes.grid(alpha=0.3)
        axes.legend(fontsize=8)
    elif robust.get("mode") == "weighted" and robust.get("best"):
        best = robust["best"]
        axes.bar(
            ["均值损失", "归一化波动"],
            [1 - best["mean_perf"], best["std_norm"]],
            color=["#2563eb", "#168064"])
        axes.set_title("加权优化候选点指标")
    else:
        axes.text(
            0.5, 0.5, "暂无可行前沿数据", ha="center", va="center")
    canvas.draw()


def factor_effects(figure, canvas, plots):
    figure.clear()
    count = len(plots)
    if count == 0:
        axes = figure.add_subplot(111)
        axes.text(0.5, 0.5, "暂无因子图", ha="center", va="center")
        canvas.draw()
        return
    columns = min(2, count)
    rows = math.ceil(count / columns)
    for index, plot in enumerate(plots):
        axes = figure.add_subplot(rows, columns, index + 1)
        axes.plot(
            plot["x"], plot["mean"], "-o", color="#1d4ed8",
            label="均值望性")
        axes.plot(
            plot["x"], plot["std"], "-s", color="#dc2626",
            label=r"$\sigma$ 归一")
        failed = [
            item for item, feasible in enumerate(plot.get("feasible", []))
            if not feasible]
        if failed:
            axes.scatter(
                [plot["x"][item] for item in failed],
                [plot["mean"][item] for item in failed],
                marker="x", color="black", label="违反约束")
        axes.set_title(plot["factor"])
        axes.grid(alpha=0.3)
        if index == 0:
            axes.legend(fontsize=7)
        axes.tick_params(labelsize=7)
    canvas.draw()
