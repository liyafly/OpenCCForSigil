# 规则编写指南 / 規則撰寫指南 / Rule Writing Guide

## 简体中文

在转换设置中打开“规则 / 沙箱”，可以添加字面规则。规则先于 OpenCC 执行；被保护的文本不会交给 OpenCC 处理，因此其中的汉字、标点和符号都会原样保留。

### 两种规则

- **精确**：把每个完整的“源文本”替换为“目标文本”。
- **保护**：把每个完整的“源文本”原样保留；目标文本留空，程序会按源文本处理。

规则按字面匹配。请把需要保留的完整文字和标点都写进源文本。署名若没有可辨别标记、只剩单字“著”，就无法安全判断它是署名还是正文；不要全局保护单字“著”，否则“慰藉著”也会保留，而不是转换为“慰藉着”。

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

V1 规则只支持字面匹配，不支持正则表达式。只读的词典检查器用于查看 OpenCC 转换结果，不会修改词典。

## 繁體中文

在轉換設定中開啟「規則 / 沙箱」，即可新增字面規則。規則會先於 OpenCC 執行；受保護的文字不會交給 OpenCC 處理，因此其中的漢字、標點和符號都會原樣保留。

### 兩種規則

- **精確**：將每個完整的「來源文字」替換為「目標文字」。
- **保護**：將每個完整的「來源文字」原樣保留；目標文字留空，程式會以來源文字作為目標。

規則依字面比對。請將需要保留的完整文字和標點都寫進來源文字。署名若沒有可辨別標記、只剩單字「著」，就無法安全判斷它是署名還是正文；不要全域保護單字「著」，否則「慰藉著」也會保留，而不會轉換為「慰藉着」。

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

V1 規則只支援字面比對，不支援正規表示式。唯讀的詞典檢查器用來查看 OpenCC 轉換結果，不會修改詞典。

## English

Open **Rules / sandbox** from the conversion settings to add a literal rule. Rules run before OpenCC. Protected text never reaches OpenCC, so its characters, punctuation, and symbols remain unchanged.

### Rule types

- **Exact** replaces each full match of **Source** with **Target**.
- **Protect** leaves each full match of **Source** unchanged. Leave **Target** blank; the source is used as the target.

Rules match literal text. Include the complete wording and punctuation to preserve. If a credit has no distinguishing marker and only contains `著`, it is ambiguous; do not protect bare `著` globally, because ordinary wording such as `慰藉著` should still convert to `慰藉着`.

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

Version 1 rules use literal matching; regular expressions are not supported. The read-only dictionary inspector shows OpenCC output and does not edit its dictionaries.
