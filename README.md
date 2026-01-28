# AAPL 策略 Web 应用

该应用通过 AkShare 下载 AAPL 日频数据，切分训练/测试集，绘制蜡烛图与 RSI/MACD，并在测试集上对比 MACD+RSI 策略与买入并持有。

## 安装
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行
```bash
streamlit run app.py
```

## 说明
- 数据集保存于 `data/aapl_daily.csv`。
- 初次下载需要联网访问 AkShare。
- 可在侧边栏刷新数据。
- 支持上传 CSV，列名包含 `open`、`close`、`high`、`low`、`volumn`/`volume`。
