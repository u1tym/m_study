# Study API仕様

本ドキュメントは、`study`スキーマ向けFastAPIの業務API仕様を日本語で定義する。  
認証はJWT(Cookie)を前提とし、JWT内`username`と`accounts.username`を突合して`accounts.id`を`aid`として利用する。

## 共通仕様

- **認証方式**: HttpOnly Cookieに格納されたJWTを検証
- **JWTクレーム利用**: `username`
- **アカウント決定**: `accounts.username = JWT.username`で`accounts.id`を取得し、以降のSQLは`aid = accounts.id`を使用
- **エラー系**:
  - Cookieなし / JWT不正 / username不正 / account不一致: `401`
  - 対象データなし: `404`
- **APIプレフィックス**: `/study/...`
- **日時**: `study.exam.q_time`はサーバ現在時刻

## A系 講義(最上位)操作

### A-1 講義作成
- **Method/Path**: `POST /study/lectures/top`
- **Input(JSON)**:
  - `lecture_name`(string, required)
- **処理**:
  - `study.lectures`へ追加
  - `pid = null`
  - `id = aidごとの採番(max+1)`
  - `dorder = aid + pid(null)ごとの採番(max+1)`
  - `title = lecture_name`
  - `explain_type = null`, `explain = null`
- **Output(JSON)**:
  - `{ "result": true }`

### A-2 講義一覧取得
- **Method/Path**: `GET /study/lectures/top`
- **Input**: なし
- **処理**:
  - `aid = current aid`
  - `pid is null`
  - `is_deleted = false`
  - `order by dorder, id`
- **Output(JSON)**:
  - `[{"lid": id, "ttl": title}, ...]`

### A-3 講義削除
- **Method/Path**: `POST /study/lectures/top/delete`
- **Input(JSON)**:
  - `lid`(int, required)
- **処理**:
  - 対象講義の`is_deleted = true`
- **Output(JSON)**:
  - `{ "result": true }`

## B系 レクチャ操作

### B-1 レクチャ追加
- **Method/Path**: `POST /study/lectures/child`
- **Input(JSON)**:
  - `parent_lid`(int, required)
  - `title`(string|null)
  - `explain_type`(string|null)
  - `explain`(string|null)
- **処理**:
  - `study.lectures`へ追加
  - `pid = parent_lid`
  - `id = aidごとの採番(max+1)`
  - `dorder = aid + pidごとの採番(max+1)`
- **Output(JSON)**:
  - `{ "result": true }`

### B-2 レクチャ順変更
- **Method/Path**: `POST /study/lectures/swap-order`
- **Input(JSON)**:
  - `lid_1`(int, required)
  - `lid_2`(int, required)
- **処理**:
  - 2件の`dorder`を入れ替え
  - 一時値を経由してユニーク制約衝突を回避
- **Output(JSON)**:
  - `{ "result": true }`

### B-3 レクチャ削除
- **Method/Path**: `POST /study/lectures/delete`
- **Input(JSON)**:
  - `lid`(int, required)
- **処理**:
  - 対象レクチャの`is_deleted = true`
- **Output(JSON)**:
  - `{ "result": true }`

### B-4 レクチャ情報取得(再帰ツリー)
- **Method/Path**: `GET /study/lectures/tree/{lid}`
- **Input(Path)**:
  - `lid`(int): ルート講義ID
- **処理**:
  - ルート(`pid is null`)から子孫を再帰取得(`is_deleted = false`)
- **Output(JSON)**:
  - `{"lid","ttl","typ","exp","chd":[同構造...]}` の再帰構造

## C系 設問操作

### C-1 設問作成
- **Method/Path**: `POST /study/questions`
- **Input(JSON)**:
  - `lid`(int)
  - `ttl`(string|null)
  - `pb1`(string, required)
  - `im1`(string|null, base64)
  - `pb2`(string|null)
  - `im2`(string|null, base64)
  - `pb3`(string|null)
  - `pb1_type`(string, optional, default `plane`): 設問 Part1 のタイプ。`plane` または `tex`（DB: `problem_1_type`）
  - `pb2_type`(string|null, optional): 設問 Part2 のタイプ。`plane` / `tex` または省略・null（DB: `problem_2_type`）
  - `pb3_type`(string|null, optional): 設問 Part3 のタイプ。`plane` / `tex` または省略・null（DB: `problem_3_type`）
  - `choices`(array, 1件以上)
    - `typ`(string|null)
    - `opt`(string|null)
    - `img`(string|null, base64)
    - `is_right`(bool, required)
- **処理**:
  - `study.questions`追加
  - `num_ans = choicesでis_right=trueの件数`
  - `study.choice`を選択肢件数分追加
  - `study.answer`へ正解選択肢のみ追加
- **Output(JSON)**:
  - `{ "result": true }`

### C-2 設問削除
- **Method/Path**: `POST /study/questions/delete`
- **Input(JSON)**:
  - `lid`(int)
  - `qid`(int)
- **処理**:
  - `study.questions.is_deleted = true`
- **Output(JSON)**:
  - `{ "result": true }`

### C-3 設問更新
- **Method/Path**: `POST /study/questions/update`
- **Input(JSON)**:
  - C-1と同等 + `qid`(更新対象)
- **処理**:
  - 既存設問を`is_deleted=true`
  - C-1相当の新規設問を作成(新`qid`)
- **Output(JSON)**:
  - `{ "result": true }`

### C-4 設問一覧取得
- **Method/Path**: `GET /study/questions/{lid}`
- **Input(Path)**:
  - `lid`(int)
- **処理**:
  - `study.questions`から`is_deleted=false`を取得
- **Output(JSON)**:
  - `{"lid": <lid>, "qes":[{"qid": id, "ttl": title}, ...]}`

### C-5 設問取得
- **Method/Path**: `GET /study/questions/{lid}/{qid}`
- **Input(Path)**:
  - `lid`(int)
  - `qid`(int): `1以上`なら指定ID、`負数`ならランダム1件
- **処理**:
  - `study.questions` 1件取得
  - `study.choice`を同`qid`で取得
- **Output(JSON)**:
  - `{"lid","ttl","pb1","im1","pb2","im2","pb3","pb1_type","pb2_type","pb3_type","num","opt":[{"cid","typ","opt","img","is_right"}...]}`（`pb1_type`〜`pb3_type` は DB の `problem_*_type` に対応。`is_right`: 当該選択肢が正解なら`true`）

## D系 回答

### D-1 回答
- **Method/Path**: `POST /study/questions/answer`
- **Input(JSON)**:
  - `lid`(int)
  - `qid`(int)
  - `answer`(int配列, 1件以上)
- **処理**:
  - `study.answer`の正解cid集合と、入力`answer`集合を比較
  - 完全一致で正解(`true`)、それ以外は不正解(`false`)
  - `study.exam`へ履歴追加
    - `id = aid,lidごと採番(max+1)`
    - `q_time = 現在時刻`
    - `is_right = 判定結果`
- **Output(JSON)**:
  - `{"result": <bool>, "right": [正解cid...]}`

## 実行方法

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Swagger UI: `http://localhost:8000/docs`
