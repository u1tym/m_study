# Study DB仕様

本ドキュメントは`study`スキーマのテーブル仕様を、他の生成AIでも再利用しやすい形式で整理したもの。

## スキーマ概要

- スキーマ名: `study`
- 主な業務:
  - 講義/レクチャの階層管理 (`lectures`)
  - 設問管理 (`questions`)
  - 設問ごとの解説 (`comment`)
  - 選択肢/正解管理 (`choice`, `answer`)
  - 回答履歴管理 (`exam`)
- 全テーブルで`aid`(accounts.id)を保持し、アカウント単位でデータ分離する。

## テーブル定義

### 1. `study.lectures` (講義・レクチャ)

- **用途**: 講義(最上位)およびその配下レクチャを同一テーブルで階層管理
- **主キー**: `(aid, id)`
- **主なカラム**:
  - `aid`(int, not null): アカウントID
  - `id`(int, not null): レクチャID(アカウント内採番)
  - `pid`(int, null): 親レクチャID。`null`は最上位(講義)
  - `dorder`(int, not null): 表示順
  - `title`(text, null): タイトル
  - `explain_type`(text, null): 内容書式
  - `explain`(text, null): 内容
  - `is_deleted`(bool, not null, default false): 論理削除
- **外部キー**:
  - `(aid) -> accounts(id)`
  - `(aid, pid) -> study.lectures(aid, id)` (自己参照)
- **ユニーク制約**:
  - `(aid, pid, dorder)` (同一親配下の並び順重複禁止)

### 2. `study.questions` (設問)

- **用途**: レクチャごとの設問本文を保持
- **主キー**: `(aid, lid, id)`
- **主なカラム**:
  - `aid`(int, not null): アカウントID
  - `lid`(int, not null): レクチャID
  - `id`(int, not null): 設問ID(同一aid,lid内採番)
  - `title`(text, null): 設問タイトル
  - `problem_1`(text, not null): 問題文1
  - `image_1_b64`(text, null): 画像1(Base64)
  - `problem_2`(text, null): 問題文2
  - `image_2_b64`(text, null): 画像2(Base64)
  - `problem_3`(text, null): 問題文3
  - `num_ans`(int, not null): 正答数
  - `is_deleted`(bool, not null, default false): 論理削除
- **外部キー**:
  - `(aid, lid) -> study.lectures(aid, id)`

### 3. `study.comment` (設問解説)

- **用途**: 設問1件につき解説本文を最大1件保持（任意。行が無い場合は解説なし）
- **主キー**: `(aid, lid, qid)`
- **主なカラム**:
  - `aid`(int, not null): アカウントID
  - `lid`(int, not null): レクチャID
  - `qid`(int, not null): 設問ID
  - `body_type`(text, not null): 解説本文のタイプ（例: `plane`, `tex`）
  - `body`(text, not null): 解説本文
- **外部キー**:
  - `(aid, lid, qid) -> study.questions(aid, lid, id)`

### 4. `study.choice` (選択肢)

- **用途**: 設問ごとの選択肢を保持
- **主キー**: `(aid, lid, qid, id)`
- **主なカラム**:
  - `aid`(int, not null): アカウントID
  - `lid`(int, not null): レクチャID
  - `qid`(int, not null): 設問ID
  - `id`(int, not null): 選択肢ID(同一aid,lid,qid内採番)
  - `option_type`(text, null): 文字列タイプ(`plane`,`tex`等)
  - `option`(text, null): 選択肢文字列
  - `image_b64`(text, null): 画像(Base64)
- **外部キー**:
  - `(aid, lid, qid) -> study.questions(aid, lid, id)`

### 5. `study.answer` (正解)

- **用途**: 設問の正解選択肢IDを保持(複数正解対応)
- **主キー**: `(aid, lid, qid, cid)`
- **主なカラム**:
  - `aid`(int, not null)
  - `lid`(int, not null)
  - `qid`(int, not null)
  - `cid`(int, not null): 正解選択肢ID
- **外部キー**:
  - `(aid, lid, qid, cid) -> study.choice(aid, lid, qid, id)`

### 6. `study.exam` (出題・回答履歴)

- **用途**: 回答実行時の出題履歴/正誤を保存
- **主キー**: `(aid, lid, id)`
- **主なカラム**:
  - `aid`(int, not null)
  - `lid`(int, not null)
  - `id`(int, not null): 履歴ID(同一aid,lid内採番)
  - `q_time`(timestamp, not null): 出題日時
  - `qid`(int, not null): 設問ID
  - `is_right`(bool, not null, default false): 正解フラグ
- **外部キー**:
  - `(aid, lid) -> study.lectures(aid, id)`
  - `(aid, lid, qid) -> study.questions(aid, lid, id)`

## リレーション要点

- `lectures` 1 - N `questions`
- `questions` 1 - 0..1 `comment`
- `questions` 1 - N `choice`
- `choice` 1 - 0..1 `answer` (正解として採用された場合)
- `questions` 1 - N `exam` (回答履歴)
- `lectures` は自己参照で木構造

## 運用上の注意

- 論理削除(`is_deleted`)を使うため、通常検索では`is_deleted=false`条件が必須。
- 採番はDBシーケンスではなく、`max(id)+1`方式を採用している。
- 並び順(`dorder`)は`(aid,pid)`単位で一意管理。
