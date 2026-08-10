# 文件恢复说明

由于移动到 `D:\AIrobot\gold-watch\` 后丢失了 8 个文件，本目录 `gold-watch_restore\` 包含完整的恢复副本。

## 恢复后的目标目录结构

```
D:\AIrobot\gold-watch\
├── .github\workflows\hourly.yml       ← 从 gold-watch_restore\.github\workflows\hourly.yml 复制
├── .gitignore                          ← 从 gold-watch_restore\.gitignore 复制
├── docs\
│   ├── index.html                      ← 从 gold-watch_restore\docs\index.html 复制
│   └── data\summary.json               ← 从 gold-watch_restore\docs\data\summary.json 复制
├── src\
│   ├── main.py                         ← 从 gold-watch_restore\src\main.py 复制
│   ├── storage.py                      ← 从 gold-watch_restore\src\storage.py 复制
│   ├── alerts\engine.py                ← 从 gold-watch_restore\src\alerts\engine.py 复制
│   └── notifiers\feishu.py             ← 从 gold-watch_restore\src\notifiers\feishu.py 复制
└── tests\test_smoke.py                 ← 从 gold-watch_restore\tests\test_smoke.py 复制
```

## 已存在且完好的文件（无需操作）

- config.json / config.yaml / requirements.txt
- src\__init__.py / src\config.py / src\models.py
- src\fetchers\__init__.py / src\fetchers\base.py / src\fetchers\jd_gold.py
- src\notifiers\__init__.py / src\notifiers\base.py
- src\alerts\__init__.py（空文件，正常）

## 一键恢复（PowerShell）

```powershell
$src = "d:\AIrobot\cheapest-flights-main\gold-watch_restore"
$dst = "D:\AIrobot\gold-watch"
Copy-Item -Path "$src\*" -Destination $dst -Recurse -Force
```

## 验证

恢复后运行：
```powershell
cd D:\AIrobot\gold-watch
python tests\test_smoke.py
# 预期: 16 passed, 0 failed
```
