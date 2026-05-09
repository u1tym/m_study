create schema study;

-- 講義
-- pidがnullは最上位 = titleが講義名
create table study.lectures (
  aid          integer not null, -- アカウントID
  id           integer not null, -- レクチャID
  
  pid          integer null,     -- 親のレクチャID（親がnullは、最上位)
  dorder       integer not null, -- 表示順 aid, pidに対して一意

  title        text    null,     -- タイトル
  explain_type text    null,     -- 内容の書式
  explain      text    null,     -- 内容

  is_deleted   bool    not null default false, -- 削除フラグ

  -- accounts.id
  constraint fk_study_lectures_aid
    foreign key (aid) references accounts(id),

  -- 親のキーへの参照制約
  constraint fk_study_lectures_aid_pid
    foreign key (aid, pid) references study.lectures(aid, id),

  -- 表示順の唯一性
  constraint uq_study_lectures_aid_pid_dorder
    unique (aid, pid, dorder),

  primary key (aid, id)
);

-- 設問
create table study.questions (
  aid         integer  not null,    -- アカウントID
  lid         integer  not null,    -- レクチャID
  id          integer  not null,    -- 設問ID（aid, lid毎に一意）
  
  title       text     null,        -- タイトル
  
  problem_1   text     not null,    -- 設問_Part_1
  image_1_b64 text     null,        -- 画像_1(Base64)
  problem_2   text     null,        -- 設問_Part_2
  image_2_b64 text     null,        -- 画像_2(Base64)
  problem_3   text     null,        -- 設問_Part_3
  
  num_ans     integer  not null,    -- 正答数

  is_deleted   bool    not null default false, -- 削除フラグ
  
  constraint fk_study_question_aid_lid
    foreign key (aid, lid) references study.lectures(aid, id),
  primary key (aid, lid, id)
);

-- 選択肢
create table study.choice (
  aid         integer not null, -- アカウントID
  lid         integer not null, -- レクチャID
  qid         integer not null, -- 設問ID
  id          integer not null, -- 選択肢ID（aid, lid, qid 毎に一意）
  
  option_type text    null,     -- 選択肢文字列のタイプ(plane, tex)
  option      text    null,     -- 選択肢文字列
  image_b64   text    null,     -- 画像
  
  constraint fk_study_choice_aid_lid_qid
    foreign key (aid, lid, qid) references study.questions(aid, lid, id),
  primary key (aid, lid, qid, id)
);

-- 正解
create table study.answer (
  aid    integer  not null,
  lid    integer  not null,
  qid    integer  not null,
  cid    integer  not null,
  
  constraint fk_study_answer_aid_lid_qid_cid
    foreign key (aid, lid, qid, cid) references study.choice(aid, lid, qid, id),
  primary key (aid, lid, qid, cid)
);

-- 出題
create table study.exam (
  aid    integer   not null,
  lid    integer   not null,
  
  id     integer   not null,
  
  q_time timestamp not null, -- 出題日時
  qid    integer   not null,
  
  is_right boolean not null default false, -- 正解フラグ
  
  constraint fk_study_exam_aid_lid
    foreign key (aid, lid) references study.lectures(aid, id),
  constraint fk_study_exam_aid_lid_qid
    foreign key (aid, lid, qid) references study.questions(aid, lid, id),
    
  primary key (aid, lid, id)
);

