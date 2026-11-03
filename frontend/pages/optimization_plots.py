"""Matplotlib rendering helpers for the optimization page."""


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
            s=18, alpha=0.6, color="#17a2b8", zorder=1)
        front = robust.get("front") or []
        if front:
            x_values = [point["obj"][0] for point in front]
            y_values = [
                point["obj"][1] for point in front
                if len(point["obj"]) > 1]
            if len(y_values) == len(x_values):
                axes.plot(
                    x_values, y_values, "-o", color="#1d4ed8",
                    lw=1.6, label="帕累托前沿", zorder=2)
                axes.lines[-1].set_picker(5)
        best = robust.get("best")
        if best and len(best["obj"]) > 1:
            label = "折中推荐解" if robust.get("mode") == "multi" else "推荐解"
            axes.scatter(
                [best["obj"][0]], [best["obj"][1]], s=160,
                marker="*", color="#f97316", edgecolors="#8f4a13",
                linewidths=.8, label=label, zorder=5)
        viewed = robust.get('viewed')
        if viewed and viewed['obj'] != best['obj']:
            axes.scatter([viewed['obj'][0]], [viewed['obj'][1]], s=110,
                         marker='D', facecolors='#c026d3', edgecolors='white', linewidths=1.2,
                         label='当前查看', zorder=6)
        labels = robust.get('plot_labels', ('望性损失（1 − 平均望性）', r'归一化标准差 $\sigma$'))
        axes.set_xlabel(labels[0])
        axes.set_ylabel(labels[1])
        axes.set_title("鲁棒性优化设计帕累托前沿")
        axes.grid(alpha=0.3)
        axes.legend(fontsize=8)
    elif robust.get("mode") == "weighted" and robust.get("best"):
        best = robust["best"]
        axes.bar(
            ["望性损失", "归一化标准差"],
            [1 - best["mean_perf"], best["std_norm"]],
            color=["#2563eb", "#168064"])
        axes.set_title("加权优化候选点指标")
    else:
        axes.text(
            0.5, 0.5, "暂无可行前沿数据", ha="center", va="center")
    canvas.draw()
