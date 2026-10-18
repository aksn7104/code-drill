# AI に「言語の設定（_language.yaml）」を作らせる指示文

新しい言語（例：javascript）を足すときは、`questions/{言語}/_language.yaml` に、その言語の**採点のきまり**を書きます。
AI に作らせるときは、下の指示文を貼り付けてください。`{言語}` の1か所を書き換えます。

| 場所 | 意味 | 例 |
|---|---|---|
| `{言語}` | 言語の名前 | JavaScript、Go、Ruby |

## 指示文（ここから下を貼り付ける）

````text
{言語} の練習問題の採点のきまりを、次の YAML の形で作ってください。出力は YAML だけにします。

- name：画面に出す言語の名前（文字）
- case_sensitive：大文字と小文字を区別して採点するか（true か false）。{言語} が、大文字と小文字を区別する言語なら true、区別しないなら false
- ignore_spaces：答えの中の余分な空白を無視するか（true か false）。ふつうは true

そして、そのきまりにした理由を、YAML のあとに1〜2行で説明してください。
````

## 見本

```yaml
name: JavaScript
case_sensitive: true
ignore_spaces: true
```

- Python・JavaScript のように大文字と小文字を区別する言語は `true`、SQL のように区別しない言語は `false` です
- このファイルがなくても動きます（その場合は、区別する・空白は無視、で採点します）
- 保存したあと、`python drill.py --check` で形式を確かめます（誤りがあれば、まとめて表示されます）
