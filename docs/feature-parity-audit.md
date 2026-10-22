# 功能同步审计：FC26 参考实现 → FC27 编辑器

> 这是开发记录：本编辑器从 FC26 版编辑器起步，2026-10-22 已完成全部功能同步与 FC27 适配。
> 方法：逐文件哈希比对 + 路由 / CLI / 前端入口 / 服务 API 对比 + 在真实存档上实测。
> 状态：**已全部同步并修复**（35 个单元测试通过，含真实存档保存回读验证）。

## 一、已同步的核心功能（无差异或仅 FC27 专属改动）

| 模块 | 状态 |
| --- | --- |
| 存档读写 / FBCHUNKS / 表结构（`core/*`） | 一致 |
| 球员编辑（属性、特性、搜索、保存草稿） | 一致（生日日期控件已补齐） |
| 球队编辑（名单、排序、号码修改） | 一致 |
| 快捷转会 / 精确转会 | 一致（占位球队过滤已补齐） |
| 国家队选拔后端流程（原位改写 RrqT 链接） | 一致（性别与 FC27 ID 适配已补齐） |
| 导出 CSV / Excel（`--export` / `--export-players`） | 一致 |
| 保存为新存档（`save_as`、容量/数量校验） | 一致 |
| CLI 参数 | FC26 的 9 个参数全部保留 |

FC27 独有、FC26 没有的功能（属于增强，不是缺失）：

- 全员年龄调整（任意年龄、保留真实月日、生日快照恢复、内置 21,972 条真实生日）
- 补齐缺失球员（以官方存档为源，自由球员方式补入，262 条差异分类）
- 现役老将回归巅峰（FIFA19 主源 + 3DM 兜底，`data/fc27_peak_fallback.csv`）
- 球员 / 球队 ID 映射层（`core/id_map.py`：球员 +1、球队 +2、自由球员 111594）

## 二、原审计发现的 6 项缺失（已全部修复）

### 1. 打开存档：原生文件选择窗口 ✅

- 点顶部「打开存档」→ 后端 `/api/pick-save` 弹 Windows 文件选择窗，选中后直接加载。
- 失败/取消时弹出备用对话框：可从文件管理器选文件（按文件名在 FC/FC27 存档目录查找）、手动输入路径、「重试系统文件选择」。
- `/api/open` 支持 `{"filename": ...}` 与 `{"path": ...}` 两种方式。
- `core/config.py` 优先搜索 FC27 的 `settings` 目录，同时兼容旧版目录名。
- 移植测试 `tests/test_open_dialog.py`（7 个用例，含弹窗失败回退）。

### 2. 国家队选拔：男足/女足体系 + FC27 ID 适配 ✅

- 新增存档驱动的国家队识别 `NameResolver.detected_national_teams()`：CxJp 球队→国籍链接 + 队名等于国家名（支持 `... Women` / `... 女足` 后缀）+ 名单多数国籍一致；缓存于 DB 对象。
- `is_national_team()` = 识别结果 ∪ 旧固定表中「队名确实像国家队」的 ID，避免 FC27 资产 ID 重排后把 `Panathinaikos`、`Motor Lublin` 误判成国家队。
- 男足/女足切换按钮 `#nationalGenderToggle`：按名单性别过滤候选池（男女共用 nationality id），并排除 5v5/Rush 占位球员与「Free Agent Managers」经理记录。
- 名单人数按实际链接数（男足 26、女足 23），`editable` 阈值为 ≥5，原位改写记录数不变。
- 候选对象补充 `position` 字段，供前端经典号码编号使用。
- 实测（FC27 官方存档 `Squads20261006`）：68 支国家队（50 男 + 18 女），转会列表 799 支球队中没有 5v5/经理池；英格兰男足候选 1509 人、英格兰女足候选 174 人，互不串性别。
- 移植/重写测试 `tests/test_national_selection.py`（8 个用例：列表、候选性别、占位排除、女足 23 人原位改写、原子性、缓存幂等）。

### 3. 按位置自动编号（经典号码）✅

- 新增「按位置自动编号（经典号码）」+「按当前排序编号」两个按钮。
- `CLASSIC_NUMBER_SLOTS`：门将 1；后卫 2/3/4/5；中场 10/8/6；前锋 9/7/11，按「位置匹配 + 能力最高」挑人，替补按 GK→后卫→中场→前锋补剩余号码。

### 4. 传奇补齐：Kempes / Rivellino + 女足开关 + 姓名行 + 生日修正 ✅

- `EXTRA_LEGENDS` = Kempes (82092)、Rivellino (191190)；`REAL_BIRTHDAYS` 修正其占位生日（135779 / 132662，均 ≥ `BIRTHDATE_MIN`）。
- 从 `legend_database.db` 的 `nqvu` 表补写 `nQVU`（editedplayernames）姓名行。
- 默认只补男足，新增「包含女足传奇」复选框（后端 `include_women` 参数）。
- 实测（官方存档）：补 167 名传奇、写 2 条姓名行；保存后回读 Kempes/Rivellino 生日有效、姓名行存在。
- 修复了带新增记录保存时的两个 FC27 编码问题（此前未被发现，任何「新增球员」保存都会触发）：
  - `contractvaliduntil` 在存档里是「2000 + 年份偏移」（30 = 2030），传奇数据库存的是 2030，直接写入会被 1 字节字段截断 → 已在导入时换算；
  - `nQVU` 字符串字段收到整数 0 会写成 `"0"`，回读为空串 → 已按字段类型转成空字符串。

### 5. 球员编辑：生日按日期修改 ✅

- 后端 `player_detail` 把 `birthdate` 以 `YYYY-MM-DD` 输出（`format: "date"`，min 1582-10-14），
  `player_service._parse_value` 接受 ISO 日期或原始天数。
- 前端 `renderField` 使用 `<input type="date">`，点击时保留当前生日便于直接选日历。
- 移植测试 `tests/test_birthdate_edit.py`（8 个用例：转换、日期回写、天数兼容、非法日期原子拒绝）。

### 6. 占位球队过滤 ✅

- `NameResolver.is_non_player_team()`（5v5/Rush、经理池）接入 `team_options`：转会/球队列表不再出现 `5v5 Team1/2`、`Free Agent Managers`。
- 女足球队 label 追加「· 女足」，男足/女足按钮据此分类。
- 自由球员池 `111594 (NG - FA)` 保留，阿森纳等真实球队不受影响。

### 7. 其它 ✅

- 生日异常名单计数保留（`invalid_birthdates`），FC27 的年龄功能更完整，无需旧生日报表。
- 移植 `tests/test_open_dialog.py`、`tests/test_birthdate_edit.py`；`tools/export_fifa19_peak.py` 不适用（FC27 已有 `tools/build_fc27_peak_fallback.py`）。

## 三、验证结果

| 验证项 | 结果 |
| --- | --- |
| 单元测试 | `python -m unittest discover -s tests` → **35 tests OK** |
| 国家队列表（FC27 官方存档） | 68 支（50 男 + 18 女），0 支占位球队混入 |
| 国家队列表（FC26 存档） | 74 支（57 男 + 17 女） |
| 男足候选池 | 性别一致、无占位/经理记录、无女足球员 |
| 女足原位改写 | 23 条 RrqT 记录数不变，保存后回读一致 |
| 传奇导入（官方存档） | 167 人 + 2 条姓名行，Kempes/Rivellino 生日有效 |
| 传奇导入（女足勾选） | 可用 206 人 / 缺失 186 人 |
| 缺失球员导入保存 | 155 人，保存后回读重扫 0 |
| Web 冒烟 | `/`、`/app.js`、`/styles.css` 200；`/api/meta` 含 gender；`/api/quick/legends` 正常 |

## 四、存档格式补充（已写入 `docs/save-format.md`）

- FC27 存档存在两种球队 ID 布局：`assetid + 2 = teamid`（官方 FC27 档）与 `assetid = teamid`（FC26 档），国家队识别不依赖固定 ID 表。
- `contractvaliduntil` 存的是「2000 + 年份」偏移，不是四位年份。
- `nQVU` 是 editedplayernames 表，用于传奇等姓名不在原姓名表里的记录。
- `CZUM.gender`：0 男 / 1 女；国家队候选必须按名单性别过滤。
