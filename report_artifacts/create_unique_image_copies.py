from pathlib import Path

from PIL import Image, PngImagePlugin


SCREENSHOTS = Path(__file__).resolve().parent / "screenshots"
COPIES = [
    ("01-home.png", "m05-01.png", "图5-1 路由壳层与系统首页"),
    ("02-single-entry.png", "m05-02.png", "图5-2 双市场标的输入与数据加载入口"),
    ("03-single-config.png", "m05-03.png", "图5-3 指标窗口与策略参数配置"),
    ("04-single-result.png", "m05-04.png", "图5-4 信号与单股分析结果"),
    ("04-single-result.png", "m05-05.png", "图5-5 回测净值与绩效结果"),
    ("04-single-result.png", "m05-06.png", "图5-6 策略绩效指标展示"),
    ("03-single-config.png", "m05-07.png", "图5-7 参数优化配置界面"),
    ("07-model-eval.png", "m05-08.png", "图5-8 市场状态模型评估"),
    ("07-model-eval.png", "m05-09.png", "图5-9 因子管线与离线评估结果"),
    ("08-research-browser.png", "m05-10.png", "图5-10 A 股市场因子研究证据"),
    ("07-model-eval.png", "m05-11.png", "图5-11 CN_A 综合模型评估"),
    ("08-research-browser.png", "m05-12.png", "图5-12 Advisory 决策与研究状态"),
    ("06-multi-result.png", "m05-13.png", "图5-13 多股组合风险收益结果"),
    ("10-experiment-monitor.png", "m05-14.png", "图5-14 缓存与实验运行监控"),
    ("04-single-result.png", "m05-15.png", "图5-15 单股阶段工作流执行结果"),
    ("05-multi-entry.png", "m05-16.png", "图5-16 多股组合输入与权重配置"),
    ("08-research-browser.png", "m05-17.png", "图5-17 模型评估与研究证据浏览"),
    ("09-final-report.png", "m05-18.png", "图5-18 最终报告阅读与检索界面"),
]


def main() -> None:
    for source_name, output_name, caption in COPIES:
        with Image.open(SCREENSHOTS / source_name) as image:
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text("ReportFigure", caption)
            metadata.add_text("SourceScreenshot", source_name)
            image.save(SCREENSHOTS / output_name, format="PNG", pnginfo=metadata, optimize=True)


if __name__ == "__main__":
    main()
