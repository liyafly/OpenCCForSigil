# 规则编写指南 / 規則撰寫指南 / Rule Writing Guide

## 简体中文

在转换设置中打开“规则 / 沙箱”，可以管理规则集并试跑规则。旧规则会保留原来的语义；新规则可选择动作、匹配方式和阶段。

### 动作和匹配方式

- **指定最终写法**：在原文上匹配，完整命中直接使用目标文本，并跳过后续转换。
- **保护原文**：在原文上匹配，命中部分不交给 OpenCC、引号或标点处理。
- **转换前替换**：在未锁定的原文上匹配，替换结果继续经过 OpenCC、引号和标点处理。
- **转换后替换**：在 OpenCC、引号和标点处理后匹配，不再进入 OpenCC。

“普通文字”会按字面匹配；“正则表达式”使用随插件附带的 `regex` VERSION1 方言。正则只匹配当前提取的文本或允许转换的属性值，不会跨越标签，也不会直接扫描或改写整份 XHTML。替换阶段同一轮只基于阶段输入匹配一次，新生成的文字不会在同阶段再次匹配。

零长度命中会被拒绝。插件限制表达式长度、单条规则命中数、整次分析的命中数、替换输出大小和匹配耗时。超时或越限会中止整次分析，不会生成可写回的部分计划。复杂表达式可从“使用模板”开始，例如署名保护模板只匹配 `◎` 后的署名标记；它不会保护正文里所有单独的“著”。

规则匹配只发生在单个提取文本片段内。`<span>` 等标签分开的文字不会拼接后再匹配。

### 署名示例

对于 `tw2sp` 和 `tw2sp_jieba`，插件默认保护 `◎【著】`、`◎著`，以及 `◎ 著`、`◎　著` 两种常见空格写法。人名仍会转换，署名标记保持不变：

```text
安迪·威爾（Andy Weir）◎【著】
→ 安迪·威尔（Andy Weir）◎【著】
安迪·威爾（Andy Weir）◎著
→ 安迪·威尔（Andy Weir）◎著
```

这些格式已内置，无需重复添加。若署名不含 `◎` 或其他稳定标记，请不要只保护单字“著”；应使用能唯一识别署名的较长字面文本，并把范围设为“当前书”，再用沙箱检查周围正文。若还要在当前书中保护 `【编者】`，添加以下规则：

| 字段 | 填写内容 |
| --- | --- |
| 类型 | 保护 |
| 方向 | 要使用规则的转换方向，例如 `tw2sp` |
| 源文本 | `【编者】` |
| 目标文本 | 留空 |
| 范围 | 当前书 |

选择“全局”可让所有书籍使用该规则；选择“当前方案”只在对应方案启用时使用；选择“当前书”则只用于当前 EPUB。`tw2sp` 方向在启用 Jieba 分词时同样适用。

### 测试和保存

1. 选择要编辑的规则集。
2. 填写类型、方向、源文本和范围。精确规则还要填写目标文本。
3. 点击“添加”，确认规则出现在列表中。
4. 在沙箱输入有代表性的文本，点击“测试”；同时检查应该保护的文字和周围仍应转换的文字。
5. 点击“保存”，并确认当前方案包含此规则集。

升级后的旧 `exact` 规则仍是“指定最终写法”，旧 `protect` 仍保留原文；它们不会被自动改成前置替换。保存或导入时会检查正则语法与替换模板，分析时只执行当前方向和范围实际生效的规则。只读词典检查器用于查看 OpenCC 转换结果，不会修改词典。

## 繁體中文

在轉換設定中開啟「規則 / 沙箱」，即可管理規則集並試跑規則。舊規則會保留原有語義；新規則可選擇動作、比對方式和階段。

### 動作和比對方式

- **指定最終寫法**：在原文比對，完整命中直接使用目標文字，並略過後續轉換。
- **保護原文**：在原文比對，命中部分不交給 OpenCC、引號或標點處理。
- **轉換前取代**：在未鎖定的原文比對，取代結果會繼續經過 OpenCC、引號和標點處理。
- **轉換後取代**：在 OpenCC、引號和標點處理後比對，不再進入 OpenCC。

「一般文字」會依字面比對；「正規表示式」使用隨附的 `regex` VERSION1 方言。正規表示式只比對目前擷取的文字或允許轉換的屬性值，不會跨越標籤，也不會直接掃描或改寫整份 XHTML。同一取代階段每輪只依階段輸入比對一次，新產生的文字不會在同階段再次比對。

零長度命中會被拒絕。外掛會限制表示式長度、單條規則命中數、整次分析命中數、取代輸出大小和比對時間。逾時或超過限制會中止整次分析，不會產生可寫回的部分計畫。可從「使用範本」開始，例如署名保護範本只比對 `◎` 後的署名標記，不會保護正文中所有單獨的「著」。

規則只會在單一擷取文字片段內比對。被 `<span>` 等標籤分開的文字不會先拼接再比對。

### 署名範例

對於 `tw2sp` 和 `tw2sp_jieba`，外掛預設會保護 `◎【著】`、`◎著`，以及 `◎ 著`、`◎　著` 兩種常見空格寫法。人名仍會轉換，署名標記則保持不變：

```text
安迪·威爾（Andy Weir）◎【著】
→ 安迪·威尔（Andy Weir）◎【著】
安迪·威爾（Andy Weir）◎著
→ 安迪·威尔（Andy Weir）◎著
```

這些格式已內建，無需重複新增。若署名不含 `◎` 或其他穩定標記，請勿只保護單字「著」；應使用能唯一識別署名的較長字面文字，並將範圍設為「目前書籍」，再用沙箱檢查周圍正文。若要只在目前書籍保護 `【编者】`，可新增以下規則：

| 欄位 | 填寫內容 |
| --- | --- |
| 類型 | 保護 |
| 方向 | 要使用規則的轉換方向，例如 `tw2sp` |
| 來源文字 | `【编者】` |
| 目標文字 | 留空 |
| 範圍 | 目前書籍 |

選擇「全域」可讓所有書籍使用此規則；選擇「目前設定檔」只在對應設定檔啟用時使用；選擇「目前書籍」則只用於目前 EPUB。`tw2sp` 方向在啟用 Jieba 分詞時同樣適用。

### 測試及儲存

1. 選擇要編輯的規則集。
2. 填寫類型、方向、來源文字和範圍。精確規則還要填寫目標文字。
3. 點擊「新增」，確認規則出現在清單中。
4. 在沙箱輸入有代表性的文字，點擊「測試」；同時檢查應受保護的文字和周圍仍應轉換的文字。
5. 點擊「儲存」，並確認目前設定檔包含此規則集。

升級後的舊 `exact` 規則仍是「指定最終寫法」，舊 `protect` 仍會保留原文；不會自動改成前置取代。儲存或匯入時會檢查正規表示式語法與取代範本，分析時只執行目前方向和範圍實際生效的規則。唯讀詞典檢查器用來查看 OpenCC 轉換結果，不會修改詞典。

## English

Open **Rules / sandbox** from the conversion settings to manage rule sets and try rules. Existing rules keep their semantics; new rules choose an action, match type, and stage.

### Actions and match types

- **Final wording** matches original text, writes the target for the full match, and skips later conversion.
- **Protect original** matches original text and keeps the match out of OpenCC, quotation, and punctuation processing.
- **Pre-replacement** matches unlocked original text; its output continues through OpenCC, quotation, and punctuation processing.
- **Post-replacement** matches after OpenCC, quotation, and punctuation processing, and does not re-enter OpenCC.

**Plain text** matches literally. **Regular expression** uses the bundled `regex` VERSION1 dialect. Expressions only match one extracted text or allowed attribute value; they do not cross tags or scan and rewrite whole XHTML. A stage matches its input once, so newly generated text is not matched again in the same stage.

Zero-length matches are rejected. The plugin caps pattern length, hits per rule, total hits, replacement output, and matching time. A timeout or limit stops the whole analysis, so it cannot produce a partial writeback plan. Start with **Templates**, such as the author-credit protection template; it matches a marked credit and does not protect every standalone `著` in prose.

Matching stays inside each extracted text fragment. Text split by tags such as `<span>` is not joined for matching.

### Author-credit example

OpenCCForSigil protects `◎【著】`, `◎著`, and the common spaced forms `◎ 著` and `◎　著` by default for both `tw2sp` and `tw2sp_jieba`. The name still converts while the marker stays intact:

```text
安迪·威爾（Andy Weir）◎【著】
→ 安迪·威尔（Andy Weir）◎【著】
安迪·威爾（Andy Weir）◎著
→ 安迪·威尔（Andy Weir）◎著
```

These forms are built in; you do not need to add them. If the credit has no `◎` or other stable marker, do not protect bare `著`; use a longer literal that uniquely identifies the credit with **Current book** scope, then test nearby prose in the sandbox. To protect `【编者】` only in the current book, add:

| Field | Value |
| --- | --- |
| Type | Protect |
| Direction | The conversion direction that should use the rule, such as `tw2sp` |
| Source | `【编者】` |
| Target | Leave blank |
| Scope | Current book |

Choose **Global** to apply the rule to every book, **Current profile** to apply it only when that profile is active, or **Current book** to keep it local to the current EPUB. The `tw2sp` direction also applies when Jieba segmentation is selected.

### Test and save

1. Select the rule set to edit.
2. Fill in Type, Direction, Source, and Scope. Exact rules also need a Target.
3. Select **Add** and check that the rule appears in the list.
4. Enter representative text in the sandbox and select **Test**. Check both the protected text and nearby text that should still convert.
5. Select **Save**, then make sure the active profile includes this rule set.

Upgraded `exact` rules remain **Final wording** and `protect` rules still keep the original; they are not silently changed to pre-replacements. Saving or importing checks regex syntax and replacement templates. Analysis executes only rules enabled for the active direction and scope. The read-only dictionary inspector shows OpenCC output and does not edit its dictionaries.
